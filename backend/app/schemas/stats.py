from __future__ import annotations

from pydantic import BaseModel


class StatsResponse(BaseModel):
    total_jobs: int
    total_resumes: int


class RuntimeEndpointMetric(BaseModel):
    endpoint: str
    requests: int
    error_rate: float
    latency_ms_p50: float | None = None
    latency_ms_p95: float | None = None


class RuntimeStatsResponse(BaseModel):
    uptime_seconds: float
    total_requests: int
    total_errors: int
    error_rate: float
    latency_ms_p50: float | None = None
    latency_ms_p95: float | None = None
    endpoints: list[RuntimeEndpointMetric]


class FairnessGroupMetric(BaseModel):
    group_value: str
    candidates_total: int
    selected_top_k: int
    selection_rate: float
    mean_model_score: float | None = None
    mean_embedding_cosine: float | None = None
    mean_years_experience: float | None = None
    positive_feedback: int = 0
    negative_feedback: int = 0
    positive_feedback_rate: float | None = None


class FairnessReport(BaseModel):
    group_by: str
    top_k_cutoff: int
    total_candidates: int
    total_runs: int
    reference_group: str | None = None
    demographic_parity_ratio: float | None = None
    groups: list[FairnessGroupMetric]
    notes: list[str] = []
