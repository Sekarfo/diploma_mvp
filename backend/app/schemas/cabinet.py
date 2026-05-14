from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class HistoryRunSummary(BaseModel):
    run_id: str
    created_at: str
    request_kind: str
    status: str
    top_k: int
    num_candidates: int
    retrieved_count: int
    returned_count: int
    existing_job_id: str | None = None
    vacancy_title: str = ""
    vacancy_description_preview: str = ""
    error_message: str | None = None


class HistoryListResponse(BaseModel):
    runs: list[HistoryRunSummary] = Field(default_factory=list)


class HistoryCandidate(BaseModel):
    final_rank: int
    resume_id: str
    final_fusion_score: float
    model_score: float
    retrieval_rank: int
    feature_snapshot: dict
    explanation: dict


class HistoryDetailResponse(BaseModel):
    run_id: str
    created_at: str
    request_kind: str
    status: str
    top_k: int
    num_candidates: int
    retrieved_count: int
    returned_count: int
    existing_job_id: str | None = None
    vacancy_title: str = ""
    vacancy_description: str = ""
    error_message: str | None = None
    request_payload: dict = Field(default_factory=dict)
    candidates: list[HistoryCandidate] = Field(default_factory=list)


class VacancySummary(BaseModel):
    vacancy_id: str
    created_at: str
    source: str
    title: str
    years_required: float
    description_preview: str
    runs_count: int
    last_run_at: str | None = None


class VacancyListResponse(BaseModel):
    vacancies: list[VacancySummary] = Field(default_factory=list)


# ── Feedback ──────────────────────────────────────────────────────────────────

FeedbackDecision = Literal["accept", "reject", "maybe", "interview"]


class FeedbackRequest(BaseModel):
    final_rank: int = Field(..., ge=1, description="Rank of the candidate in the shortlist")
    decision: FeedbackDecision
    rating: int | None = Field(None, ge=1, le=5)
    note: str | None = Field(None, max_length=2000)


class FeedbackEntry(BaseModel):
    feedback_id: str
    run_id: str
    final_rank: int
    resume_id: str
    decision: str
    rating: int | None = None
    note: str | None = None
    created_at: str
    updated_at: str


class FeedbackResponse(BaseModel):
    feedback_id: str
    run_id: str
    final_rank: int
    resume_id: str
    decision: str
    rating: int | None = None
    note: str | None = None
    created_at: str
    updated_at: str


class FeedbackListResponse(BaseModel):
    run_id: str
    feedbacks: list[FeedbackEntry] = Field(default_factory=list)


# ── Vacancy file parser ───────────────────────────────────────────────────────

class ParsedVacancyResponse(BaseModel):
    title: str
    description: str
    years_required: float | None = None
    skills: list[str] = Field(default_factory=list)
    file_name: str
    char_count: int
    page_count: int
    parse_warnings: list[str] = Field(default_factory=list)
