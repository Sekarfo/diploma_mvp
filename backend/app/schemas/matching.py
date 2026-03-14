from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class MatchJobRequest(BaseModel):
    job_id: str = Field(default="ad_hoc_job")
    job_title: str = Field(min_length=1)
    job_description: str = Field(min_length=1)
    top_k: int = Field(default=10, ge=1, le=100)


class MatchedCandidate(BaseModel):
    resume_id: str
    full_name: str | None = None
    headline: str | None = None
    baseline_score: float
    model_score: float
    baseline_rank: int
    model_rank: int
    explanation: str
    matched_skills: list[str] = Field(default_factory=list)
    bm25_score: float
    normalized_bm25_score: float
    exact_skill_overlap_count: float
    exact_skill_overlap_ratio: float
    title_token_overlap_ratio: float
    years_experience_estimate: float

    model_config = ConfigDict(extra="allow")


class MatchJobResponse(BaseModel):
    job_id: str
    total_candidates: int
    ranked_candidates: list[MatchedCandidate]
