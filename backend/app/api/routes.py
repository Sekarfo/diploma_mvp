from __future__ import annotations

from functools import lru_cache

import pandas as pd
from fastapi import APIRouter, HTTPException, status

from backend.app.schemas import (
    MatchJobRequest,
    MatchJobResponse,
    RankCandidatesRequest,
    RankCandidatesResponse,
)
from backend.app.services import JobMatchingService, RankingService

router = APIRouter()


@lru_cache(maxsize=1)
def get_ranking_service() -> RankingService:
    return RankingService()


@lru_cache(maxsize=1)
def get_job_matching_service() -> JobMatchingService:
    return JobMatchingService(ranking_service=get_ranking_service())


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/rank-candidates", response_model=RankCandidatesResponse)
def rank_candidates(payload: RankCandidatesRequest) -> RankCandidatesResponse:
    if not payload.candidates:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="candidates list must not be empty.",
        )

    try:
        ranking_service = get_ranking_service()
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Model loading failed: {exc}",
        ) from exc
    except Exception as exc:  # pragma: no cover - defensive MVP guard
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected model loading failure: {exc}",
        ) from exc

    candidates_df = pd.DataFrame([candidate.model_dump() for candidate in payload.candidates])

    try:
        ranked_df = ranking_service.rank_candidates(candidates_df)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:  # pragma: no cover - defensive MVP guard
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ranking failed: {exc}",
        ) from exc

    ranked_candidates = ranked_df.to_dict(orient="records")
    return RankCandidatesResponse(
        job_id=payload.job_id,
        total_candidates=len(ranked_candidates),
        ranked_candidates=ranked_candidates,
    )


@router.post("/match-job", response_model=MatchJobResponse)
def match_job(payload: MatchJobRequest) -> MatchJobResponse:
    try:
        matching_service = get_job_matching_service()
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Model loading failed: {exc}",
        ) from exc
    except Exception as exc:  # pragma: no cover - defensive MVP guard
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected startup failure: {exc}",
        ) from exc

    try:
        ranked_df, total_candidates = matching_service.match_job(
            job_title=payload.job_title,
            job_description=payload.job_description,
            top_k=payload.top_k,
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Local candidate data error: {exc}",
        ) from exc
    except Exception as exc:  # pragma: no cover - defensive MVP guard
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Matching failed: {exc}",
        ) from exc

    ranked_candidates = ranked_df.to_dict(orient="records")
    return MatchJobResponse(
        job_id=payload.job_id,
        total_candidates=total_candidates,
        ranked_candidates=ranked_candidates,
    )
