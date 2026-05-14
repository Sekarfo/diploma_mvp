from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Final

from src.ml.config import FEATURE_COLUMNS

EXPECTED_RANKER_FEATURES: list[str] = list(FEATURE_COLUMNS)

_TRUE_VALUES: Final[set[str]] = {"1", "true", "yes", "on"}


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass(frozen=True)
class Settings:
    root_dir: Path
    data_dir: Path
    raw_data_dir: Path
    embeddings_dir: Path

    jobs_parquet_candidates: tuple[Path, ...]
    jobs_csv_candidates: tuple[Path, ...]
    resumes_parquet_candidates: tuple[Path, ...]
    resumes_csv_candidates: tuple[Path, ...]
    job_embeddings_candidates: tuple[Path, ...]
    resume_embeddings_candidates: tuple[Path, ...]
    ranker_model_candidates: tuple[Path, ...]
    ranker_features_candidates: tuple[Path, ...]

    elasticsearch_url: str
    elasticsearch_username: str | None
    elasticsearch_password: str | None
    elasticsearch_index_name: str

    cross_encoder_model: str
    cross_encoder_max_length: int
    cross_encoder_batch_size: int
    cross_encoder_cascade_enabled: bool
    cross_encoder_cascade_top_m: int
    cross_encoder_cascade_default_score: float

    database_url: str
    db_schema_autocreate: bool
    auth_session_ttl_minutes: int
    auth_password_pepper: str

    default_top_k: int
    default_num_candidates: int
    max_top_k: int
    max_num_candidates: int


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    root_dir = Path(__file__).resolve().parents[3]
    _load_env_file(root_dir / ".env")
    data_dir = root_dir / "data"
    raw_data_dir = data_dir / "Clear"
    embeddings_dir = data_dir / "embeddings"
    models_dir = root_dir / "models"

    return Settings(
        root_dir=root_dir,
        data_dir=data_dir,
        raw_data_dir=raw_data_dir,
        embeddings_dir=embeddings_dir,
        jobs_parquet_candidates=tuple(),
        jobs_csv_candidates=(raw_data_dir / "jobs_clean.csv",),
        resumes_parquet_candidates=tuple(),
        resumes_csv_candidates=(raw_data_dir / "resumes_clean.csv",),
        job_embeddings_candidates=(embeddings_dir / "job_embeddings.npy",),
        resume_embeddings_candidates=(embeddings_dir / "resume_embeddings.npy",),
        ranker_model_candidates=(models_dir / "lgbm_ranker.joblib",),
        ranker_features_candidates=(models_dir / "ranker_features.joblib",),
        elasticsearch_url=os.getenv("ELASTICSEARCH_URL", "http://127.0.0.1:9200"),
        elasticsearch_username=os.getenv("ELASTICSEARCH_USERNAME"),
        elasticsearch_password=os.getenv("ELASTICSEARCH_PASSWORD"),
        elasticsearch_index_name=os.getenv("ELASTICSEARCH_INDEX", "resumes_index"),
        cross_encoder_model=os.getenv(
            "CROSS_ENCODER_MODEL", "cross-encoder/ms-marco-MiniLM-L-12-v2"
        ),
        cross_encoder_max_length=int(os.getenv("CROSS_ENCODER_MAX_LENGTH", "512")),
        cross_encoder_batch_size=int(os.getenv("CROSS_ENCODER_BATCH_SIZE", "64")),
        cross_encoder_cascade_enabled=(
            os.getenv("CROSS_ENCODER_CASCADE_ENABLED", "true").strip().lower() in _TRUE_VALUES
        ),
        cross_encoder_cascade_top_m=int(os.getenv("CROSS_ENCODER_CASCADE_TOP_M", "200")),
        cross_encoder_cascade_default_score=float(
            os.getenv("CROSS_ENCODER_CASCADE_DEFAULT_SCORE", "0.0")
        ),
        database_url=os.getenv(
            "DATABASE_URL",
            "postgresql://postgres:postgres@127.0.0.1:5432/hr_shortlist",
        ),
        db_schema_autocreate=os.getenv("DB_SCHEMA_AUTOCREATE", "true").strip().lower() in _TRUE_VALUES,
        auth_session_ttl_minutes=int(os.getenv("AUTH_SESSION_TTL_MINUTES", "10080")),
        auth_password_pepper=os.getenv("AUTH_PASSWORD_PEPPER", ""),
        default_top_k=20,
        default_num_candidates=100,
        max_top_k=200,
        max_num_candidates=5000,
    )
