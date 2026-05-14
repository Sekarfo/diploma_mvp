from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from backend.app.api import router as api_router
from backend.app.limiter import limiter
from backend.app.services import ensure_postgres_schema
from backend.app.services.errors import DatabaseUnavailableError
from backend.app.services.runtime_metrics_service import get_runtime_metrics_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Job-Resume Ranking MVP", version="0.1.0")

# Attach limiter so slowapi decorators work on the router
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS (Fix #10) 
_cors_origins_raw = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost,http://localhost:80")
_cors_origins = [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)

app.include_router(api_router)

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="ui")


# Request ID middleware (Fix #11) 
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# Runtime metrics middleware
@app.middleware("http")
async def collect_runtime_metrics(request: Request, call_next):
    if request.url.path.startswith("/ui"):
        return await call_next(request)

    metrics_service = get_runtime_metrics_service()
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        latency_ms = float((time.perf_counter() - started) * 1000.0)
        metrics_service.record(
            method=request.method,
            path=request.url.path,
            status_code=500,
            latency_ms=latency_ms,
        )
        raise

    latency_ms = float((time.perf_counter() - started) * 1000.0)
    metrics_service.record(
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        latency_ms=latency_ms,
    )
    return response


# Startup (Fix #7) 
@app.on_event("startup")
def startup_initialize_services() -> None:
    
    from backend.app.config import get_settings as _gs
    _s = _gs()
    if not _s.auth_password_pepper or _s.auth_password_pepper in ("change-me-in-prod", "changeme"):
        logger.warning(
            "AUTH_PASSWORD_PEPPER is empty or uses a default placeholder value. "
            "Set a strong random secret in production via the AUTH_PASSWORD_PEPPER env variable. "
            "Changing this value after users are created will invalidate all existing passwords."
        )

    try:
        ensure_postgres_schema()
        logger.info("PostgreSQL schema verified.")
    except DatabaseUnavailableError as exc:
        logger.warning("PostgreSQL schema initialization skipped: %s", exc)

    try:
        from backend.app.api.routes import get_shortlist_service
        get_shortlist_service().artifact_service.get_artifacts()
        logger.info("ML artifacts preloaded successfully.")
    except Exception as exc:
        logger.warning("ML artifact preload failed (will retry on first request): %s", exc)


_cleanup_task: asyncio.Task | None = None
SESSION_CLEANUP_INTERVAL_SECONDS = 6 * 3600   
SESSION_GRACE_PERIOD = "1 day"                 


async def _session_cleanup_loop() -> None:
    await asyncio.sleep(30)   
    while True:
        try:
            from backend.app.services.db_service import db_connection
            with db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        f"DELETE FROM user_sessions "
                        f"WHERE expires_at < now() - INTERVAL '{SESSION_GRACE_PERIOD}'"
                    )
                    deleted = cur.rowcount
            if deleted > 0:
                logger.info("Session cleanup: removed %d expired session(s).", deleted)
            else:
                logger.debug("Session cleanup: no expired sessions found.")
        except Exception as exc:
            logger.warning("Session cleanup failed (will retry in %dh): %s",
                           SESSION_CLEANUP_INTERVAL_SECONDS // 3600, exc)
        await asyncio.sleep(SESSION_CLEANUP_INTERVAL_SECONDS)


@app.on_event("startup")
async def start_session_cleanup() -> None:
    global _cleanup_task
    _cleanup_task = asyncio.create_task(_session_cleanup_loop())
    logger.info(
        "Session cleanup task started — interval: %dh, grace period: %s.",
        SESSION_CLEANUP_INTERVAL_SECONDS // 3600,
        SESSION_GRACE_PERIOD,
    )


@app.on_event("shutdown")
async def stop_session_cleanup() -> None:
    global _cleanup_task
    if _cleanup_task and not _cleanup_task.done():
        _cleanup_task.cancel()
        try:
            await _cleanup_task
        except asyncio.CancelledError:
            pass
    logger.info("Session cleanup task stopped.")


@app.get("/")
def root() -> RedirectResponse:
    return RedirectResponse(url="/ui")
