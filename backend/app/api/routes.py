from __future__ import annotations

import logging
import time
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, status

from backend.app.schemas import (
    AuthMeResponse,
    AuthResponse,
    FairnessReport,
    FeedbackListResponse,
    FeedbackRequest,
    FeedbackResponse,
    GlobalModelExplanationResponse,
    HistoryDetailResponse,
    HistoryListResponse,
    JobDetailResponse,
    JobsResponse,
    ParsedVacancyResponse,
    RuntimeStatsResponse,
    ShortlistRequest,
    ShortlistResponse,
    SignInRequest,
    SignOutResponse,
    SignUpRequest,
    StatsResponse,
    VacancyListResponse,
    VacancyShortlistRequest,
    VacancyShortlistResponse,
)
from backend.app.limiter import limiter
from backend.app.services import (
    AuthenticatedUser,
    AuthService,
    FairnessService,
    HistoryService,
    ShortlistService,
    get_auth_service,
    get_current_user,
    get_fairness_service,
    get_history_service,
    get_model_explanation_service,
    get_runtime_metrics_service,
)
from backend.app.services.db_service import db_connection
from backend.app.services.errors import (
    ArtifactLoadError,
    AuthenticationError,
    DatabaseUnavailableError,
    ElasticsearchUnavailableError,
    EmptyRetrievalError,
    HistoryNotFoundError,
    HistoryPersistenceError,
    JobNotFoundError,
    RankingError,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@lru_cache(maxsize=1)
def get_shortlist_service() -> ShortlistService:
    return ShortlistService()


def _model_to_dict(model_obj) -> dict:
    if hasattr(model_obj, "model_dump"):
        return model_obj.model_dump()
    return model_obj.dict()


def _map_error_to_http(exc: Exception) -> HTTPException:
    if isinstance(exc, AuthenticationError):
        return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))
    if isinstance(exc, JobNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, HistoryNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, EmptyRetrievalError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, ElasticsearchUnavailableError):
        return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    if isinstance(exc, (DatabaseUnavailableError,)):
        return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    if isinstance(exc, (ArtifactLoadError, RankingError, FileNotFoundError, HistoryPersistenceError)):
        return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"Unexpected server error: {exc}",
    )


@router.get("/health")
def health() -> dict:
    checks: dict[str, str] = {}

    # Database check
    try:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        checks["database"] = "ok"
    except Exception as exc:
        logger.warning("Health check: database unavailable — %s", exc)
        checks["database"] = "unavailable"

    # ML artifacts check
    try:
        get_shortlist_service().artifact_service.get_artifacts()
        checks["artifacts"] = "ok"
    except Exception as exc:
        logger.warning("Health check: artifacts unavailable — %s", exc)
        checks["artifacts"] = "unavailable"

    overall = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return {"status": overall, **checks}


@router.post("/auth/signup", response_model=AuthResponse)
@limiter.limit("10/minute")
def signup(payload: SignUpRequest, request: Request) -> AuthResponse:
    logger.info("POST /auth/signup request started email=%s", payload.email)
    try:
        service: AuthService = get_auth_service()
        result = service.signup(
            email=payload.email,
            password=payload.password,
            full_name=payload.full_name,
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
        )
        return AuthResponse(**result)
    except Exception as exc:
        logger.exception("POST /auth/signup failed email=%s: %s", payload.email, exc)
        raise _map_error_to_http(exc) from exc


@router.post("/auth/signin", response_model=AuthResponse)
def signin(payload: SignInRequest, request: Request) -> AuthResponse:
    logger.info("POST /auth/signin request started email=%s", payload.email)
    try:
        service: AuthService = get_auth_service()
        result = service.signin(
            email=payload.email,
            password=payload.password,
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
        )
        return AuthResponse(**result)
    except Exception as exc:
        logger.exception("POST /auth/signin failed email=%s: %s", payload.email, exc)
        raise _map_error_to_http(exc) from exc


@router.get("/auth/me", response_model=AuthMeResponse)
def auth_me(current_user: AuthenticatedUser = Depends(get_current_user)) -> AuthMeResponse:
    return AuthMeResponse(
        id=current_user.user_id,
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        is_active=current_user.is_active,
    )


@router.post("/auth/signout", response_model=SignOutResponse)
def signout(request: Request, current_user: AuthenticatedUser = Depends(get_current_user)) -> SignOutResponse:
    del current_user
    auth_header = str(request.headers.get("authorization", ""))
    token = ""
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
    try:
        service: AuthService = get_auth_service()
        service.signout(token)
        return SignOutResponse(status="signed_out")
    except Exception as exc:
        logger.exception("POST /auth/signout failed: %s", exc)
        raise _map_error_to_http(exc) from exc


@router.get("/cabinet/history", response_model=HistoryListResponse)
def list_history(
    limit: int = Query(default=50, ge=1, le=200),
    current_user: AuthenticatedUser = Depends(get_current_user),
    history_service: HistoryService = Depends(get_history_service),
) -> HistoryListResponse:
    logger.info("GET /cabinet/history request started user_id=%s limit=%s", current_user.user_id, limit)
    try:
        runs = history_service.list_history(user_id=current_user.user_id, limit=limit)
        return HistoryListResponse(runs=runs)
    except Exception as exc:
        logger.exception("GET /cabinet/history failed user_id=%s: %s", current_user.user_id, exc)
        raise _map_error_to_http(exc) from exc


@router.get("/cabinet/history/{run_id}", response_model=HistoryDetailResponse)
def get_history_detail(
    run_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
    history_service: HistoryService = Depends(get_history_service),
) -> HistoryDetailResponse:
    logger.info("GET /cabinet/history/%s request started user_id=%s", run_id, current_user.user_id)
    try:
        detail = history_service.get_run_detail(user_id=current_user.user_id, run_id=run_id)
        return HistoryDetailResponse(**detail)
    except Exception as exc:
        logger.exception(
            "GET /cabinet/history/%s failed user_id=%s: %s",
            run_id,
            current_user.user_id,
            exc,
        )
        raise _map_error_to_http(exc) from exc


@router.get("/cabinet/vacancies", response_model=VacancyListResponse)
def list_vacancies(
    limit: int = Query(default=100, ge=1, le=500),
    current_user: AuthenticatedUser = Depends(get_current_user),
    history_service: HistoryService = Depends(get_history_service),
) -> VacancyListResponse:
    logger.info("GET /cabinet/vacancies request started user_id=%s limit=%s", current_user.user_id, limit)
    try:
        vacancies = history_service.list_vacancies(user_id=current_user.user_id, limit=limit)
        return VacancyListResponse(vacancies=vacancies)
    except Exception as exc:
        logger.exception("GET /cabinet/vacancies failed user_id=%s: %s", current_user.user_id, exc)
        raise _map_error_to_http(exc) from exc


@router.get("/jobs", response_model=JobsResponse)
def list_jobs() -> JobsResponse:
    logger.info("GET /jobs request started")
    try:
        service = get_shortlist_service()
        jobs = service.list_jobs()
        return JobsResponse(jobs=jobs)
    except Exception as exc:
        logger.exception("GET /jobs failed: %s", exc)
        raise _map_error_to_http(exc) from exc


@router.get("/jobs/{job_id}", response_model=JobDetailResponse)
def get_job(job_id: str) -> JobDetailResponse:
    logger.info("GET /jobs/%s request started", job_id)
    try:
        service = get_shortlist_service()
        job = service.get_job(job_id=job_id)
        return JobDetailResponse(**job)
    except Exception as exc:
        logger.exception("GET /jobs/%s failed: %s", job_id, exc)
        raise _map_error_to_http(exc) from exc


@router.get("/stats", response_model=StatsResponse)
def get_stats() -> StatsResponse:
    logger.info("GET /stats request started")
    try:
        service = get_shortlist_service()
        stats = service.get_stats()
        return StatsResponse(**stats)
    except Exception as exc:
        logger.exception("GET /stats failed: %s", exc)
        raise _map_error_to_http(exc) from exc


@router.get("/stats/runtime", response_model=RuntimeStatsResponse)
def get_runtime_stats() -> RuntimeStatsResponse:
    logger.info("GET /stats/runtime request started")
    try:
        metrics_service = get_runtime_metrics_service()
        return RuntimeStatsResponse(**metrics_service.snapshot())
    except Exception as exc:
        logger.exception("GET /stats/runtime failed: %s", exc)
        raise _map_error_to_http(exc) from exc


@router.get("/stats/explanations/global", response_model=GlobalModelExplanationResponse)
def get_global_model_explanation() -> GlobalModelExplanationResponse:
    logger.info("GET /stats/explanations/global request started")
    try:
        service = get_model_explanation_service()
        return GlobalModelExplanationResponse(**service.get_global_explanation())
    except Exception as exc:
        logger.exception("GET /stats/explanations/global failed: %s", exc)
        raise _map_error_to_http(exc) from exc


@router.get("/stats/fairness", response_model=FairnessReport)
def get_fairness_report(
    group_by: str = Query(default="experience_bucket"),
    top_k_cutoff: int = Query(default=10, ge=1, le=200),
    run_id: str | None = Query(default=None),
    limit_runs: int = Query(default=200, ge=1, le=1000),
    current_user: AuthenticatedUser = Depends(get_current_user),
    fairness_service: FairnessService = Depends(get_fairness_service),
) -> FairnessReport:
    """Group-level selection-rate / score / feedback audit over historical runs.

    Supported `group_by` values: experience_bucket, experience_match, skill_overlap_bucket.
    When `run_id` is omitted, aggregates over the user's recent runs (capped by limit_runs).
    """
    logger.info(
        "GET /stats/fairness user_id=%s group_by=%s top_k=%s run_id=%s",
        current_user.user_id, group_by, top_k_cutoff, run_id,
    )
    try:
        report = fairness_service.compute(
            user_id=current_user.user_id,
            group_by=group_by,
            top_k_cutoff=top_k_cutoff,
            run_id=run_id,
            limit_runs=limit_runs,
        )
        return FairnessReport(**report)
    except Exception as exc:
        logger.exception(
            "GET /stats/fairness failed user_id=%s: %s", current_user.user_id, exc
        )
        raise _map_error_to_http(exc) from exc


@router.post("/shortlist", response_model=ShortlistResponse)
@limiter.limit("20/minute")
def shortlist(
    request: Request,
    payload: ShortlistRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    history_service: HistoryService = Depends(get_history_service),
) -> ShortlistResponse:
    logger.info(
        "POST /shortlist request started user_id=%s job_id=%s top_k=%s num_candidates=%s",
        current_user.user_id,
        payload.job_id,
        payload.top_k,
        payload.num_candidates,
    )
    started = time.perf_counter()
    try:
        service = get_shortlist_service()
        result = service.shortlist(
            job_id=payload.job_id,
            top_k=payload.top_k,
            num_candidates=payload.num_candidates,
        )
        latency_ms = int((time.perf_counter() - started) * 1000.0)
        run_id: str | None = None
        try:
            run_id = history_service.record_existing_job_shortlist(
                user_id=current_user.user_id,
                request_payload=_model_to_dict(payload),
                result_payload=result,
                latency_ms=latency_ms,
            )
        except Exception as history_exc:
            logger.warning(
                "POST /shortlist history persistence skipped user_id=%s job_id=%s: %s",
                current_user.user_id,
                payload.job_id,
                history_exc,
            )
        logger.info(
            "POST /shortlist completed user_id=%s job_id=%s retrieved=%s ranked=%s",
            current_user.user_id,
            payload.job_id,
            result["retrieved_count"],
            result["total_candidates"],
        )
        return ShortlistResponse(**result, run_id=run_id)
    except Exception as exc:
        logger.exception("POST /shortlist failed user_id=%s job_id=%s: %s", current_user.user_id, payload.job_id, exc)
        raise _map_error_to_http(exc) from exc


@router.post("/shortlist/vacancy", response_model=VacancyShortlistResponse)
@limiter.limit("20/minute")
def shortlist_for_vacancy(
    request: Request,
    payload: VacancyShortlistRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    history_service: HistoryService = Depends(get_history_service),
) -> VacancyShortlistResponse:
    logger.info(
        "POST /shortlist/vacancy request started user_id=%s title=%s top_k=%s num_candidates=%s",
        current_user.user_id,
        payload.vacancy_title,
        payload.top_k,
        payload.num_candidates,
    )
    started = time.perf_counter()
    try:
        service = get_shortlist_service()
        result = service.shortlist_for_vacancy(
            vacancy_title=payload.vacancy_title,
            vacancy_description=payload.vacancy_description,
            top_k=payload.top_k,
            num_candidates=payload.num_candidates,
            job_years_required=payload.job_years_required,
            job_skills_norm=payload.job_skills_norm,
        )
        latency_ms = int((time.perf_counter() - started) * 1000.0)
        run_id: str | None = None
        try:
            run_id = history_service.record_custom_vacancy_shortlist(
                user_id=current_user.user_id,
                request_payload=_model_to_dict(payload),
                result_payload=result,
                latency_ms=latency_ms,
            )
        except Exception as history_exc:
            logger.warning(
                "POST /shortlist/vacancy history persistence skipped user_id=%s title=%s: %s",
                current_user.user_id,
                payload.vacancy_title,
                history_exc,
            )
        logger.info(
            "POST /shortlist/vacancy completed user_id=%s retrieved=%s ranked=%s proxy_job=%s",
            current_user.user_id,
            result["retrieved_count"],
            result["total_candidates"],
            result["proxy_job_id"],
        )
        return VacancyShortlistResponse(**result, run_id=run_id)
    except Exception as exc:
        logger.exception("POST /shortlist/vacancy failed user_id=%s: %s", current_user.user_id, exc)
        raise _map_error_to_http(exc) from exc


# Feedback endpoints 

@router.post("/shortlist/{run_id}/feedback", response_model=FeedbackResponse)
@limiter.limit("60/minute")
def submit_feedback(
    request: Request,
    run_id: str,
    payload: FeedbackRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    history_service: HistoryService = Depends(get_history_service),
) -> FeedbackResponse:
    logger.info(
        "POST /shortlist/%s/feedback user_id=%s rank=%s decision=%s",
        run_id, current_user.user_id, payload.final_rank, payload.decision,
    )
    try:
        result = history_service.submit_feedback(
            user_id=current_user.user_id,
            run_id=run_id,
            final_rank=payload.final_rank,
            decision=payload.decision,
            rating=payload.rating,
            note=payload.note,
        )
        return FeedbackResponse(**result)
    except Exception as exc:
        logger.exception("POST /shortlist/%s/feedback failed: %s", run_id, exc)
        raise _map_error_to_http(exc) from exc


@router.delete("/shortlist/{run_id}/feedback/{final_rank}", status_code=204)
def delete_feedback(
    run_id: str,
    final_rank: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    history_service: HistoryService = Depends(get_history_service),
) -> None:
    logger.info(
        "DELETE /shortlist/%s/feedback/%s user_id=%s", run_id, final_rank, current_user.user_id
    )
    try:
        history_service.delete_feedback(
            user_id=current_user.user_id,
            run_id=run_id,
            final_rank=final_rank,
        )
    except Exception as exc:
        logger.exception("DELETE /shortlist/%s/feedback/%s failed: %s", run_id, final_rank, exc)
        raise _map_error_to_http(exc) from exc


@router.get("/shortlist/{run_id}/feedback", response_model=FeedbackListResponse)
def get_run_feedback(
    run_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
    history_service: HistoryService = Depends(get_history_service),
) -> FeedbackListResponse:
    logger.info(
        "GET /shortlist/%s/feedback user_id=%s", run_id, current_user.user_id
    )
    try:
        feedbacks = history_service.list_run_feedback(
            user_id=current_user.user_id,
            run_id=run_id,
        )
        return FeedbackListResponse(run_id=run_id, feedbacks=feedbacks)
    except Exception as exc:
        logger.exception("GET /shortlist/%s/feedback failed: %s", run_id, exc)
        raise _map_error_to_http(exc) from exc


#  Vacancy file parser

@router.post("/vacancies/parse", response_model=ParsedVacancyResponse)
@limiter.limit("20/minute")
async def parse_vacancy_file(
    request: Request,
    file: UploadFile,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ParsedVacancyResponse:
    """
    Upload a PDF or DOCX vacancy file.
    Returns extracted title, description, years_required and skills.
    The caller should review the fields and pass them to POST /shortlist/vacancy.
    """
    logger.info(
        "POST /vacancies/parse user_id=%s filename=%s content_type=%s size=%s",
        current_user.user_id,
        file.filename,
        file.content_type,
        file.size,
    )
    from backend.app.services.vacancy_parser_service import VacancyParserService
    svc = VacancyParserService()
    try:
        content = await file.read()
        result = svc.parse(
            content=content,
            file_name=file.filename or "upload",
            content_type=file.content_type or "",
        )
        return ParsedVacancyResponse(
            title=result.title,
            description=result.description,
            years_required=result.years_required,
            skills=result.skills,
            file_name=result.file_name,
            char_count=result.char_count,
            page_count=result.page_count,
            parse_warnings=result.parse_warnings,
        )
    except (ValueError, ImportError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("POST /vacancies/parse failed user_id=%s: %s", current_user.user_id, exc)
        raise HTTPException(status_code=500, detail=f"File parsing failed: {exc}") from exc

