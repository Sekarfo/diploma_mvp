from __future__ import annotations

from pydantic import BaseModel, Field


class ShortlistRequest(BaseModel):
    job_id: str = Field(min_length=1)
    top_k: int = Field(default=20, ge=1, le=200)
    num_candidates: int = Field(default=100, ge=1, le=5000)


class VacancyShortlistRequest(BaseModel):
    vacancy_title: str = Field(min_length=1)
    vacancy_description: str = Field(min_length=1)
    top_k: int = Field(default=20, ge=1, le=200)
    num_candidates: int = Field(default=100, ge=1, le=5000)
    job_years_required: float | None = Field(default=None, ge=0.0, le=60.0)
    job_skills_norm: list[str] | None = None


class ShapFactor(BaseModel):
    feature: str
    label: str
    impact: float
    raw_value: str
    description: str


class CandidateExplanation(BaseModel):
    matched_skills: list[str]
    missing_skills: list[str]
    experience_summary: str
    title_summary: str
    baseline_score: float | None = None
    top_positive_factors: list[ShapFactor] = Field(default_factory=list)
    top_negative_factors: list[ShapFactor] = Field(default_factory=list)
    raw_feature_values: dict[str, str] = Field(default_factory=dict)


class ShortlistCandidate(BaseModel):
    final_rank: int
    resume_id: str
    resume_text: str
    model_score: float
    score: float
    score_label: str
    retrieval_rank: int
    retrieval_score_raw: float
    retrieval_score_norm: float
    reranker_score_raw: float
    reranker_score_norm: float
    fusion_alpha: float
    fusion_beta: float
    retrieval_contribution: float
    reranker_contribution: float
    final_fusion_score: float
    embedding_cosine: float
    skill_overlap_count: int
    skill_overlap_ratio: float
    title_overlap_ratio: float
    resume_years_experience: float
    job_years_required: float
    years_gap: float
    experience_match_flag: int
    explanation: CandidateExplanation


class ShortlistResponse(BaseModel):
    job_id: str
    job_title: str
    total_candidates: int
    retrieved_count: int
    top_k: int
    num_candidates: int
    requested_top_k: int | None = None
    requested_num_candidates: int | None = None
    max_available_candidates: int | None = None
    run_id: str | None = None    # set after history persistence
    candidates: list[ShortlistCandidate]


class VacancyShortlistResponse(ShortlistResponse):
    proxy_job_id: str
