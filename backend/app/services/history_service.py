from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

from backend.app.config import Settings, get_settings
from backend.app.services.db_service import db_connection
from backend.app.services.errors import HistoryNotFoundError, HistoryPersistenceError


class HistoryService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def record_existing_job_shortlist(
        self,
        *,
        user_id: str,
        request_payload: dict[str, Any],
        result_payload: dict[str, Any],
        latency_ms: int | None = None,
    ) -> str:
        existing_job_id = str(request_payload.get("job_id", "")).strip()
        if not existing_job_id:
            raise HistoryPersistenceError("Cannot persist history: job_id is missing.")
        return self._record_run(
            user_id=user_id,
            request_kind="existing_job",
            request_payload=request_payload,
            result_payload=result_payload,
            existing_job_id=existing_job_id,
            vacancy_id=None,
            latency_ms=latency_ms,
        )

    def record_custom_vacancy_shortlist(
        self,
        *,
        user_id: str,
        request_payload: dict[str, Any],
        result_payload: dict[str, Any],
        latency_ms: int | None = None,
    ) -> str:
        title = str(request_payload.get("vacancy_title", "")).strip()
        description = str(request_payload.get("vacancy_description", "")).strip()
        years_required = request_payload.get("job_years_required")
        skills_norm = request_payload.get("job_skills_norm", [])

        if not title or not description:
            raise HistoryPersistenceError("Cannot persist custom vacancy history: title/description missing.")

        vacancy_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        try:
            with db_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO vacancies (
                            id, owner_user_id, source, title, description, years_required,
                            skills_norm, parser_payload, created_at, updated_at
                        ) VALUES (
                            %s, %s, 'manual', %s, %s, %s, %s, %s::jsonb, %s, %s
                        )
                        """,
                        (
                            vacancy_id,
                            user_id,
                            title,
                            description,
                            years_required,
                            list(skills_norm or []),  # text[] column — pass Python list directly
                            json.dumps({}),
                            now,
                            now,
                        ),
                    )
        except Exception as exc:
            raise HistoryPersistenceError(f"Failed to persist custom vacancy metadata: {exc}") from exc

        return self._record_run(
            user_id=user_id,
            request_kind="custom_vacancy",
            request_payload=request_payload,
            result_payload=result_payload,
            existing_job_id=None,
            vacancy_id=vacancy_id,
            latency_ms=latency_ms,
        )

    def list_history(self, *, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
        bounded_limit = max(1, min(int(limit), 200))
        try:
            with db_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT
                            r.id,
                            r.created_at,
                            r.request_kind,
                            r.status,
                            r.top_k,
                            r.num_candidates,
                            r.retrieved_count,
                            r.returned_count,
                            r.existing_job_id,
                            r.error_message,
                            v.title,
                            v.description
                        FROM shortlist_runs r
                        LEFT JOIN vacancies v ON v.id = r.vacancy_id
                        WHERE r.user_id = %s
                        ORDER BY r.created_at DESC
                        LIMIT %s
                        """,
                        (user_id, bounded_limit),
                    )
                    rows = cursor.fetchall()
        except Exception as exc:
            raise HistoryPersistenceError(f"Failed to load history list: {exc}") from exc

        results: list[dict[str, Any]] = []
        for row in rows:
            (
                run_id,
                created_at,
                request_kind,
                status,
                top_k,
                num_candidates,
                retrieved_count,
                returned_count,
                existing_job_id,
                error_message,
                vacancy_title,
                vacancy_description,
            ) = row

            description_preview = (str(vacancy_description or "")[:180]).strip()
            if vacancy_description and len(str(vacancy_description)) > 180:
                description_preview += "..."

            results.append(
                {
                    "run_id": str(run_id),
                    "created_at": self._as_iso(created_at),
                    "request_kind": str(request_kind),
                    "status": str(status),
                    "top_k": int(top_k),
                    "num_candidates": int(num_candidates),
                    "retrieved_count": int(retrieved_count or 0),
                    "returned_count": int(returned_count or 0),
                    "existing_job_id": str(existing_job_id) if existing_job_id else None,
                    "vacancy_title": str(vacancy_title or ""),
                    "vacancy_description_preview": description_preview,
                    "error_message": str(error_message) if error_message else None,
                }
            )
        return results

    def list_vacancies(self, *, user_id: str, limit: int = 100) -> list[dict[str, Any]]:
        bounded_limit = max(1, min(int(limit), 500))
        try:
            with db_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT
                            v.id,
                            v.created_at,
                            v.source,
                            v.title,
                            v.description,
                            v.years_required,
                            COUNT(r.id) AS runs_count,
                            MAX(r.created_at) AS last_run_at
                        FROM vacancies v
                        LEFT JOIN shortlist_runs r ON r.vacancy_id = v.id
                        WHERE v.owner_user_id = %s
                        GROUP BY v.id, v.created_at, v.source, v.title, v.description, v.years_required
                        ORDER BY v.created_at DESC
                        LIMIT %s
                        """,
                        (user_id, bounded_limit),
                    )
                    rows = cursor.fetchall()
        except Exception as exc:
            raise HistoryPersistenceError(f"Failed to load vacancy list: {exc}") from exc

        results: list[dict[str, Any]] = []
        for row in rows:
            (
                vacancy_id,
                created_at,
                source,
                title,
                description,
                years_required,
                runs_count,
                last_run_at,
            ) = row

            description_preview = (str(description or "")[:180]).strip()
            if description and len(str(description)) > 180:
                description_preview += "..."

            results.append(
                {
                    "vacancy_id": str(vacancy_id),
                    "created_at": self._as_iso(created_at),
                    "source": str(source),
                    "title": str(title or ""),
                    "years_required": float(years_required or 0.0),
                    "description_preview": description_preview,
                    "runs_count": int(runs_count or 0),
                    "last_run_at": self._as_iso(last_run_at) if last_run_at else None,
                }
            )
        return results

    def get_run_detail(self, *, user_id: str, run_id: str) -> dict[str, Any]:
        try:
            with db_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT
                            r.id,
                            r.created_at,
                            r.request_kind,
                            r.status,
                            r.top_k,
                            r.num_candidates,
                            r.retrieved_count,
                            r.returned_count,
                            r.existing_job_id,
                            r.error_message,
                            r.request_payload,
                            v.title,
                            v.description
                        FROM shortlist_runs r
                        LEFT JOIN vacancies v ON v.id = r.vacancy_id
                        WHERE r.user_id = %s AND r.id = %s
                        LIMIT 1
                        """,
                        (user_id, run_id),
                    )
                    run_row = cursor.fetchone()
                    if run_row is None:
                        raise HistoryNotFoundError("History run not found.")

                    cursor.execute(
                        """
                        SELECT
                            final_rank,
                            resume_id,
                            final_fusion_score,
                            model_score,
                            retrieval_rank,
                            feature_snapshot,
                            explanation_json
                        FROM shortlist_candidates
                        WHERE run_id = %s
                        ORDER BY final_rank ASC
                        """,
                        (run_id,),
                    )
                    candidate_rows = cursor.fetchall()
        except (HistoryPersistenceError, HistoryNotFoundError):
            raise
        except Exception as exc:
            raise HistoryPersistenceError(f"Failed to load history detail: {exc}") from exc

        (
            db_run_id,
            created_at,
            request_kind,
            status,
            top_k,
            num_candidates,
            retrieved_count,
            returned_count,
            existing_job_id,
            error_message,
            request_payload,
            vacancy_title,
            vacancy_description,
        ) = run_row

        candidates: list[dict[str, Any]] = []
        for candidate_row in candidate_rows:
            (
                final_rank,
                resume_id,
                final_fusion_score,
                model_score,
                retrieval_rank,
                feature_snapshot,
                explanation_json,
            ) = candidate_row
            candidates.append(
                {
                    "final_rank": int(final_rank),
                    "resume_id": str(resume_id),
                    "final_fusion_score": float(final_fusion_score or 0.0),
                    "model_score": float(model_score or 0.0),
                    "retrieval_rank": int(retrieval_rank or 0),
                    "feature_snapshot": self._parse_json_column(feature_snapshot),
                    "explanation": self._parse_json_column(explanation_json),
                }
            )

        return {
            "run_id": str(db_run_id),
            "created_at": self._as_iso(created_at),
            "request_kind": str(request_kind),
            "status": str(status),
            "top_k": int(top_k),
            "num_candidates": int(num_candidates),
            "retrieved_count": int(retrieved_count or 0),
            "returned_count": int(returned_count or 0),
            "existing_job_id": str(existing_job_id) if existing_job_id else None,
            "vacancy_title": str(vacancy_title or ""),
            "vacancy_description": str(vacancy_description or ""),
            "error_message": str(error_message) if error_message else None,
            "request_payload": self._parse_json_column(request_payload),
            "candidates": candidates,
        }

    def _record_run(
        self,
        *,
        user_id: str,
        request_kind: str,
        request_payload: dict[str, Any],
        result_payload: dict[str, Any],
        existing_job_id: str | None,
        vacancy_id: str | None,
        latency_ms: int | None,
    ) -> str:
        run_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        top_k = int(result_payload.get("top_k", request_payload.get("top_k", 20)))
        num_candidates = int(result_payload.get("num_candidates", request_payload.get("num_candidates", 100)))
        retrieved_count = int(result_payload.get("retrieved_count", 0))
        returned_count = int(result_payload.get("total_candidates", 0))

        try:
            with db_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO shortlist_runs (
                            id, user_id, vacancy_id, request_kind, existing_job_id, status,
                            top_k, num_candidates, retrieved_count, returned_count,
                            model_version, retrieval_index, request_payload, error_message, latency_ms, created_at
                        ) VALUES (
                            %s, %s, %s, %s, %s, 'success',
                            %s, %s, %s, %s,
                            %s, %s, %s::jsonb, NULL, %s, %s
                        )
                        """,
                        (
                            run_id,
                            user_id,
                            vacancy_id,
                            request_kind,
                            existing_job_id,
                            top_k,
                            num_candidates,
                            retrieved_count,
                            returned_count,
                            str(self.settings.ranker_model_candidates[0].name) if self.settings.ranker_model_candidates else "unknown",
                            self.settings.elasticsearch_index_name,
                            json.dumps(request_payload),
                            latency_ms,
                            now,
                        ),
                    )

                    for candidate in result_payload.get("candidates", []):
                        feature_snapshot = {
                            "embedding_cosine": candidate.get("embedding_cosine"),
                            "skill_overlap_count": candidate.get("skill_overlap_count"),
                            "skill_overlap_ratio": candidate.get("skill_overlap_ratio"),
                            "title_overlap_ratio": candidate.get("title_overlap_ratio"),
                            "resume_years_experience": candidate.get("resume_years_experience"),
                            "job_years_required": candidate.get("job_years_required"),
                            "years_gap": candidate.get("years_gap"),
                            "experience_match_flag": candidate.get("experience_match_flag"),
                            "retrieval_score_raw": candidate.get("retrieval_score_raw"),
                            "retrieval_score_norm": candidate.get("retrieval_score_norm"),
                            "reranker_score_raw": candidate.get("reranker_score_raw"),
                            "reranker_score_norm": candidate.get("reranker_score_norm"),
                        }
                        cursor.execute(
                            """
                            INSERT INTO shortlist_candidates (
                                run_id, final_rank, resume_id, final_fusion_score, model_score,
                                retrieval_rank, feature_snapshot, explanation_json
                            ) VALUES (
                                %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb
                            )
                            """,
                            (
                                run_id,
                                int(candidate.get("final_rank", 0)),
                                str(candidate.get("resume_id", "")),
                                float(candidate.get("final_fusion_score", candidate.get("score", 0.0))),
                                float(candidate.get("model_score", 0.0)),
                                int(candidate.get("retrieval_rank", 0)),
                                json.dumps(feature_snapshot),
                                json.dumps(candidate.get("explanation", {})),
                            ),
                        )
        except Exception as exc:
            raise HistoryPersistenceError(f"Failed to persist shortlist history: {exc}") from exc

        return run_id

    @staticmethod
    def _as_iso(value: Any) -> str:
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value)

    # ── Feedback ──────────────────────────────────────────────────────────────

    @staticmethod
    def _validate_uuid(value: str, name: str = "id") -> None:
        try:
            uuid.UUID(str(value))
        except ValueError:
            raise HistoryNotFoundError(f"Invalid {name}: '{value}'.")

    def submit_feedback(
        self,
        *,
        user_id: str,
        run_id: str,
        final_rank: int,
        decision: str,
        rating: int | None,
        note: str | None,
    ) -> dict[str, Any]:
        self._validate_uuid(run_id, "run_id")
        now = datetime.now(timezone.utc)
        feedback_id = str(uuid.uuid4())

        try:
            with db_connection() as connection:
                with connection.cursor() as cursor:
                    # Verify the run belongs to this user
                    cursor.execute(
                        "SELECT id FROM shortlist_runs WHERE id = %s AND user_id = %s",
                        (run_id, user_id),
                    )
                    if cursor.fetchone() is None:
                        raise HistoryNotFoundError("Shortlist run not found.")

                    # Look up the internal candidate id by rank
                    cursor.execute(
                        """
                        SELECT id, resume_id FROM shortlist_candidates
                        WHERE run_id = %s AND final_rank = %s
                        """,
                        (run_id, final_rank),
                    )
                    cand_row = cursor.fetchone()
                    if cand_row is None:
                        raise HistoryNotFoundError(
                            f"Candidate with rank {final_rank} not found in this run."
                        )
                    candidate_id, resume_id = cand_row

                    # Upsert: create or update feedback for (user_id, candidate_id)
                    cursor.execute(
                        """
                        INSERT INTO recruiter_feedback (
                            id, run_id, candidate_id, user_id,
                            decision, rating, note, created_at, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (user_id, candidate_id) DO UPDATE SET
                            decision   = EXCLUDED.decision,
                            rating     = EXCLUDED.rating,
                            note       = EXCLUDED.note,
                            updated_at = EXCLUDED.updated_at
                        RETURNING id, created_at, updated_at
                        """,
                        (
                            feedback_id,
                            run_id,
                            candidate_id,
                            user_id,
                            decision,
                            rating,
                            note,
                            now,
                            now,
                        ),
                    )
                    row = cursor.fetchone()
                    actual_id, created_at, updated_at = row
        except (HistoryNotFoundError, HistoryPersistenceError):
            raise
        except Exception as exc:
            raise HistoryPersistenceError(f"Failed to persist feedback: {exc}") from exc

        return {
            "feedback_id": str(actual_id),
            "run_id": run_id,
            "final_rank": final_rank,
            "resume_id": str(resume_id),
            "decision": decision,
            "rating": rating,
            "note": note,
            "created_at": self._as_iso(created_at),
            "updated_at": self._as_iso(updated_at),
        }

    def list_run_feedback(
        self, *, user_id: str, run_id: str
    ) -> list[dict[str, Any]]:
        self._validate_uuid(run_id, "run_id")
        try:
            with db_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT id FROM shortlist_runs WHERE id = %s AND user_id = %s",
                        (run_id, user_id),
                    )
                    if cursor.fetchone() is None:
                        raise HistoryNotFoundError("Shortlist run not found.")

                    cursor.execute(
                        """
                        SELECT
                            f.id,
                            f.decision,
                            f.rating,
                            f.note,
                            f.created_at,
                            f.updated_at,
                            c.final_rank,
                            c.resume_id
                        FROM recruiter_feedback f
                        JOIN shortlist_candidates c ON c.id = f.candidate_id
                        WHERE f.run_id = %s AND f.user_id = %s
                        ORDER BY c.final_rank ASC
                        """,
                        (run_id, user_id),
                    )
                    rows = cursor.fetchall()
        except (HistoryNotFoundError, HistoryPersistenceError):
            raise
        except Exception as exc:
            raise HistoryPersistenceError(f"Failed to load feedback: {exc}") from exc

        return [
            {
                "feedback_id": str(row[0]),
                "decision": str(row[1]),
                "rating": int(row[2]) if row[2] is not None else None,
                "note": str(row[3]) if row[3] is not None else None,
                "created_at": self._as_iso(row[4]),
                "updated_at": self._as_iso(row[5]),
                "final_rank": int(row[6]),
                "resume_id": str(row[7]),
                "run_id": run_id,
            }
            for row in rows
        ]

    def delete_feedback(self, *, user_id: str, run_id: str, final_rank: int) -> bool:
        """Remove a feedback entry. Returns True if a row was deleted, False if none existed."""
        try:
            with db_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        DELETE FROM recruiter_feedback
                        WHERE user_id = %s
                          AND candidate_id = (
                              SELECT id FROM shortlist_candidates
                              WHERE run_id = %s AND final_rank = %s
                              LIMIT 1
                          )
                        """,
                        (user_id, run_id, final_rank),
                    )
                    return cursor.rowcount > 0
        except Exception as exc:
            raise HistoryPersistenceError(f"Failed to delete feedback: {exc}") from exc

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_json_column(value: Any) -> Any:
        if value is None:
            return {}
        if isinstance(value, (dict, list)):
            return value
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return {}
            try:
                return json.loads(text)
            except Exception:
                return value
        return value


@lru_cache(maxsize=1)
def get_history_service() -> HistoryService:
    return HistoryService()
