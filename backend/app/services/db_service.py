from __future__ import annotations

import logging
import sys
from contextlib import contextmanager
from typing import Generator

from backend.app.config import get_settings
from backend.app.services.errors import DatabaseUnavailableError

logger = logging.getLogger(__name__)

try:
    import psycopg
    from psycopg_pool import ConnectionPool
except Exception:  # pragma: no cover
    psycopg = None  # type: ignore[assignment]
    ConnectionPool = None  # type: ignore[assignment]


_pool: "ConnectionPool | None" = None


def _require_psycopg() -> None:
    if psycopg is None or ConnectionPool is None:
        raise DatabaseUnavailableError(
            (
                "Missing dependency: psycopg / psycopg-pool. "
                f"Current interpreter: {sys.executable}. "
                "Run: pip install 'psycopg[binary]>=3.2.0' psycopg-pool>=3.2.0"
            )
        )


def _get_pool() -> "ConnectionPool":
    """Return the module-level connection pool, creating it on first call."""
    global _pool
    _require_psycopg()
    if _pool is None:
        settings = get_settings()
        _pool = ConnectionPool(
            settings.database_url,
            min_size=1,
            max_size=10,
            open=True,
            reconnect_timeout=30,
        )
        logger.info(
            "PostgreSQL connection pool created (min=1 max=10) → %s",
            settings.database_url.split("@")[-1],  # log host/db, not credentials
        )
    return _pool


@contextmanager
def db_connection() -> Generator:
    """Yield a connection from the pool; auto-commit on success, rollback on error."""
    pool = _get_pool()
    _inside_yield = False
    try:
        with pool.connection() as connection:
            try:
                _inside_yield = True
                yield connection
                _inside_yield = False
                connection.commit()
            except Exception:
                connection.rollback()
                raise
    except DatabaseUnavailableError:
        raise
    except Exception as exc:
        if _inside_yield:
            # Exception raised by application code inside the yield block —
            # do NOT wrap it; let the original type propagate (e.g. AuthenticationError).
            raise
        raise DatabaseUnavailableError(f"Failed to get DB connection from pool: {exc}") from exc


_SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id UUID PRIMARY KEY,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        full_name TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'hr' CHECK (role IN ('hr', 'admin')),
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        last_login_at TIMESTAMPTZ
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS user_sessions (
        id UUID PRIMARY KEY,
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        refresh_token_hash TEXT NOT NULL UNIQUE,
        user_agent TEXT,
        ip_address TEXT,
        expires_at TIMESTAMPTZ NOT NULL,
        revoked_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS vacancies (
        id UUID PRIMARY KEY,
        owner_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        source TEXT NOT NULL CHECK (source IN ('manual', 'upload', 'existing_job')),
        existing_job_id TEXT,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        years_required DOUBLE PRECISION,
        skills_norm JSONB NOT NULL DEFAULT '[]'::jsonb,
        original_filename TEXT,
        parser_payload JSONB,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS shortlist_runs (
        id UUID PRIMARY KEY,
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        vacancy_id UUID REFERENCES vacancies(id) ON DELETE SET NULL,
        request_kind TEXT NOT NULL CHECK (request_kind IN ('existing_job', 'custom_vacancy')),
        existing_job_id TEXT,
        status TEXT NOT NULL CHECK (status IN ('success', 'failed')),
        top_k INTEGER NOT NULL CHECK (top_k > 0),
        num_candidates INTEGER NOT NULL CHECK (num_candidates > 0),
        retrieved_count INTEGER,
        returned_count INTEGER,
        model_version TEXT,
        retrieval_index TEXT,
        request_payload JSONB NOT NULL,
        error_message TEXT,
        latency_ms INTEGER,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS shortlist_candidates (
        id BIGSERIAL PRIMARY KEY,
        run_id UUID NOT NULL REFERENCES shortlist_runs(id) ON DELETE CASCADE,
        final_rank INTEGER NOT NULL,
        resume_id TEXT NOT NULL,
        final_fusion_score DOUBLE PRECISION,
        model_score DOUBLE PRECISION,
        retrieval_rank INTEGER,
        feature_snapshot JSONB,
        explanation_json JSONB,
        UNIQUE (run_id, final_rank),
        UNIQUE (run_id, resume_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS recruiter_feedback (
        id UUID PRIMARY KEY,
        run_id UUID NOT NULL REFERENCES shortlist_runs(id) ON DELETE CASCADE,
        candidate_id BIGINT NOT NULL REFERENCES shortlist_candidates(id) ON DELETE CASCADE,
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        decision TEXT NOT NULL CHECK (decision IN ('accept', 'reject', 'maybe', 'interview')),
        rating SMALLINT CHECK (rating BETWEEN 1 AND 5),
        note TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE (user_id, candidate_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_vacancies_owner_created ON vacancies(owner_user_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_runs_user_created ON shortlist_runs(user_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_candidates_run_rank ON shortlist_candidates(run_id, final_rank)",
    "CREATE INDEX IF NOT EXISTS idx_feedback_run ON recruiter_feedback(run_id)",
    # Fix #5: partial index on active sessions token hash — avoids full table scan on every auth request
    "CREATE INDEX IF NOT EXISTS idx_sessions_token_hash ON user_sessions(refresh_token_hash) WHERE revoked_at IS NULL",
]

_MIGRATION_STATEMENTS = [
    # shortlist_runs backfill for older schemas
    "ALTER TABLE shortlist_runs ADD COLUMN IF NOT EXISTS vacancy_id UUID",
    "ALTER TABLE shortlist_runs ADD COLUMN IF NOT EXISTS request_kind TEXT NOT NULL DEFAULT 'existing_job'",
    "ALTER TABLE shortlist_runs ADD COLUMN IF NOT EXISTS existing_job_id TEXT",
    "ALTER TABLE shortlist_runs ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'success'",
    "ALTER TABLE shortlist_runs ADD COLUMN IF NOT EXISTS top_k INTEGER NOT NULL DEFAULT 20",
    "ALTER TABLE shortlist_runs ADD COLUMN IF NOT EXISTS num_candidates INTEGER NOT NULL DEFAULT 100",
    "ALTER TABLE shortlist_runs ADD COLUMN IF NOT EXISTS retrieved_count INTEGER",
    "ALTER TABLE shortlist_runs ADD COLUMN IF NOT EXISTS returned_count INTEGER",
    "ALTER TABLE shortlist_runs ADD COLUMN IF NOT EXISTS model_version TEXT",
    "ALTER TABLE shortlist_runs ADD COLUMN IF NOT EXISTS retrieval_index TEXT",
    "ALTER TABLE shortlist_runs ADD COLUMN IF NOT EXISTS request_payload JSONB NOT NULL DEFAULT '{}'::jsonb",
    "ALTER TABLE shortlist_runs ADD COLUMN IF NOT EXISTS error_message TEXT",
    "ALTER TABLE shortlist_runs ADD COLUMN IF NOT EXISTS latency_ms INTEGER",
    # shortlist_candidates backfill for older schemas
    "ALTER TABLE shortlist_candidates ADD COLUMN IF NOT EXISTS final_fusion_score DOUBLE PRECISION",
    "ALTER TABLE shortlist_candidates ADD COLUMN IF NOT EXISTS model_score DOUBLE PRECISION",
    "ALTER TABLE shortlist_candidates ADD COLUMN IF NOT EXISTS retrieval_rank INTEGER",
    "ALTER TABLE shortlist_candidates ADD COLUMN IF NOT EXISTS feature_snapshot JSONB",
    "ALTER TABLE shortlist_candidates ADD COLUMN IF NOT EXISTS explanation_json JSONB",
    # vacancies backfill for profile queries — nullable intentionally for legacy rows
    "ALTER TABLE vacancies ADD COLUMN IF NOT EXISTS owner_user_id UUID",
    "ALTER TABLE vacancies ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'manual'",
    "ALTER TABLE vacancies ADD COLUMN IF NOT EXISTS years_required DOUBLE PRECISION",
    "ALTER TABLE vacancies ADD COLUMN IF NOT EXISTS skills_norm JSONB NOT NULL DEFAULT '[]'::jsonb",
    "ALTER TABLE vacancies ADD COLUMN IF NOT EXISTS parser_payload JSONB",
    # Fix #5: add token index on existing DBs (idempotent via IF NOT EXISTS)
    "CREATE INDEX IF NOT EXISTS idx_sessions_token_hash ON user_sessions(refresh_token_hash) WHERE revoked_at IS NULL",
]


def ensure_postgres_schema() -> None:
    settings = get_settings()
    if not settings.db_schema_autocreate:
        return

    # Schema statements (CREATE TABLE / INDEX IF NOT EXISTS) run together — safe to batch.
    with db_connection() as connection:
        with connection.cursor() as cursor:
            for statement in _SCHEMA_STATEMENTS:
                cursor.execute(statement)

    # Migration statements run individually so a single failure doesn't roll back others.
    for statement in _MIGRATION_STATEMENTS:
        try:
            with db_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(statement)
        except Exception as exc:
            logger.warning("Migration statement skipped (%s): %.120s", type(exc).__name__, statement.strip())
