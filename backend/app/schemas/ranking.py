from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CandidateRow(BaseModel):
    resume_id: str
    bm25_score: float
    normalized_bm25_score: float
    exact_skill_overlap_count: float
    exact_skill_overlap_ratio: float
    title_token_overlap_ratio: float
    years_experience_estimate: float

    model_config = ConfigDict(extra="allow")


class RankCandidatesRequest(BaseModel):
    job_id: str
    candidates: list[CandidateRow] = Field(min_length=1)


class RankedCandidate(CandidateRow):
    model_score: float


class RankCandidatesResponse(BaseModel):
    job_id: str
    total_candidates: int
    ranked_candidates: list[RankedCandidate]

