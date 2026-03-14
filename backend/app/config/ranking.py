from __future__ import annotations

from pathlib import Path

FEATURE_COLUMNS = [
    "bm25_score",
    "normalized_bm25_score",
    "exact_skill_overlap_count",
    "exact_skill_overlap_ratio",
    "title_token_overlap_ratio",
    "years_experience_estimate",
]

# backend/app/config/ranking.py -> repo root is parents[3]
RANKER_MODEL_PATH = Path(__file__).resolve().parents[3] / "models" / "ranker_model.json"

