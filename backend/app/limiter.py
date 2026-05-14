from __future__ import annotations

from starlette.requests import Request
from slowapi import Limiter


def _real_ip(request: Request) -> str:
    return (
        request.headers.get("X-Real-IP")
        or request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or (request.client.host if request.client else "unknown")
    )


limiter = Limiter(key_func=_real_ip, default_limits=["200/minute"])
