from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any

from backend.app.services.db_service import db_connection
from backend.app.services.errors import HistoryPersistenceError

logger = logging.getLogger(__name__)


# Decisions persisted by recruiter_feedback.decision (CHECK constraint in db_service.py).
_POSITIVE_DECISIONS = {"accept", "interview"}
_NEGATIVE_DECISIONS = {"reject"}

_SUPPORTED_GROUPS = {
    "experience_bucket",
    "experience_match",
    "skill_overlap_bucket",
}


def _experience_bucket(years: float | None) -> str:
    if years is None:
        return "unknown"
    try:
        y = float(years)
    except (TypeError, ValueError):
        return "unknown"
    if y < 1.0:
        return "0-1y"
    if y < 3.0:
        return "1-3y"
    if y < 6.0:
        return "3-6y"
    if y < 10.0:
        return "6-10y"
    return "10y+"


def _skill_overlap_bucket(count: float | None) -> str:
    if count is None:
        return "unknown"
    try:
        c = int(float(count))
    except (TypeError, ValueError):
        return "unknown"
    if c <= 0:
        return "0"
    if c <= 2:
        return "1-2"
    if c <= 5:
        return "3-5"
    if c <= 10:
        return "6-10"
    return "11+"


def _experience_match_bucket(flag: Any) -> str:
    try:
        return "meets" if int(flag) == 1 else "below"
    except (TypeError, ValueError):
        return "unknown"


def _extract_group(snapshot: dict[str, Any], group_by: str) -> str:
    if group_by == "experience_bucket":
        return _experience_bucket(snapshot.get("resume_years_experience"))
    if group_by == "experience_match":
        return _experience_match_bucket(snapshot.get("experience_match_flag"))
    if group_by == "skill_overlap_bucket":
        return _skill_overlap_bucket(snapshot.get("skill_overlap_count"))
    return "unknown"


def _parse_snapshot(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            data = json.loads(value)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


def _safe_mean(values: list[float]) -> float | None:
    cleaned = [v for v in values if v is not None]
    if not cleaned:
        return None
    return float(sum(cleaned) / len(cleaned))


class FairnessService:
    """Group-level selection/score audit over historical shortlist runs.

    Operates entirely on persisted data (`shortlist_candidates.feature_snapshot`
    + `recruiter_feedback.decision`) — no model inference required. For each
    HR-defined sensitive group (experience bucket, skill-overlap bucket,
    experience-match flag) reports:

      - selection_rate = (# selected in top-K) / (# retrieved into pool)
      - mean_model_score (LightGBM raw score)
      - mean_embedding_cosine
      - mean_years_experience
      - positive_feedback_rate = (accept+interview) / (accept+reject+interview+maybe)

    `demographic_parity_ratio` is the minimum selection_rate / maximum selection_rate
    across groups (the classic "four-fifths" / 80% rule baseline).
    """

    def supported_groups(self) -> list[str]:
        return sorted(_SUPPORTED_GROUPS)

    def compute(
        self,
        *,
        user_id: str,
        group_by: str,
        top_k_cutoff: int = 10,
        run_id: str | None = None,
        limit_runs: int = 200,
    ) -> dict[str, Any]:
        if group_by not in _SUPPORTED_GROUPS:
            raise ValueError(
                f"Unsupported group_by='{group_by}'. Choose from: {sorted(_SUPPORTED_GROUPS)}"
            )
        if top_k_cutoff <= 0:
            raise ValueError("top_k_cutoff must be > 0")

        try:
            with db_connection() as connection:
                with connection.cursor() as cursor:
                    if run_id is not None:
                        cursor.execute(
                            "SELECT id FROM shortlist_runs WHERE id = %s AND user_id = %s",
                            (run_id, user_id),
                        )
                        if cursor.fetchone() is None:
                            raise HistoryPersistenceError(
                                f"Shortlist run {run_id} not found for current user."
                            )
                        cursor.execute(
                            """
                            SELECT
                                c.id,
                                c.run_id,
                                c.final_rank,
                                c.model_score,
                                c.feature_snapshot,
                                f.decision
                            FROM shortlist_candidates c
                            LEFT JOIN recruiter_feedback f
                                ON f.candidate_id = c.id AND f.user_id = %s
                            WHERE c.run_id = %s
                            """,
                            (user_id, run_id),
                        )
                        rows = cursor.fetchall()
                        distinct_runs = 1
                    else:
                        cursor.execute(
                            """
                            SELECT id FROM shortlist_runs
                            WHERE user_id = %s
                            ORDER BY created_at DESC
                            LIMIT %s
                            """,
                            (user_id, max(1, min(int(limit_runs), 1000))),
                        )
                        run_ids = [r[0] for r in cursor.fetchall()]
                        if not run_ids:
                            return {
                                "group_by": group_by,
                                "top_k_cutoff": top_k_cutoff,
                                "total_candidates": 0,
                                "total_runs": 0,
                                "reference_group": None,
                                "demographic_parity_ratio": None,
                                "groups": [],
                                "notes": ["No shortlist runs found for this user yet."],
                            }
                        cursor.execute(
                            """
                            SELECT
                                c.id,
                                c.run_id,
                                c.final_rank,
                                c.model_score,
                                c.feature_snapshot,
                                f.decision
                            FROM shortlist_candidates c
                            LEFT JOIN recruiter_feedback f
                                ON f.candidate_id = c.id AND f.user_id = %s
                            WHERE c.run_id = ANY(%s)
                            """,
                            (user_id, run_ids),
                        )
                        rows = cursor.fetchall()
                        distinct_runs = len(run_ids)
        except HistoryPersistenceError:
            raise
        except Exception as exc:
            raise HistoryPersistenceError(f"Failed to load fairness audit data: {exc}") from exc

        groups: dict[str, dict[str, Any]] = {}
        for row in rows:
            _, _, final_rank, model_score, snapshot_raw, decision = row
            snapshot = _parse_snapshot(snapshot_raw)
            group_value = _extract_group(snapshot, group_by)
            bucket = groups.setdefault(
                group_value,
                {
                    "candidates_total": 0,
                    "selected_top_k": 0,
                    "model_scores": [],
                    "embedding_cosines": [],
                    "years": [],
                    "positive_feedback": 0,
                    "negative_feedback": 0,
                    "feedback_total": 0,
                },
            )
            bucket["candidates_total"] += 1

            try:
                rank_int = int(final_rank) if final_rank is not None else None
            except (TypeError, ValueError):
                rank_int = None
            if rank_int is not None and rank_int <= top_k_cutoff:
                bucket["selected_top_k"] += 1

            if model_score is not None:
                try:
                    bucket["model_scores"].append(float(model_score))
                except (TypeError, ValueError):
                    pass

            emb = snapshot.get("embedding_cosine")
            if emb is not None:
                try:
                    bucket["embedding_cosines"].append(float(emb))
                except (TypeError, ValueError):
                    pass
            years = snapshot.get("resume_years_experience")
            if years is not None:
                try:
                    bucket["years"].append(float(years))
                except (TypeError, ValueError):
                    pass

            if decision is not None:
                decision_str = str(decision).strip().lower()
                bucket["feedback_total"] += 1
                if decision_str in _POSITIVE_DECISIONS:
                    bucket["positive_feedback"] += 1
                elif decision_str in _NEGATIVE_DECISIONS:
                    bucket["negative_feedback"] += 1

        group_metrics: list[dict[str, Any]] = []
        for group_value, bucket in groups.items():
            total = bucket["candidates_total"]
            selected = bucket["selected_top_k"]
            feedback_total = bucket["feedback_total"]
            selection_rate = (selected / total) if total > 0 else 0.0
            positive_rate = (
                bucket["positive_feedback"] / feedback_total if feedback_total > 0 else None
            )
            group_metrics.append(
                {
                    "group_value": group_value,
                    "candidates_total": total,
                    "selected_top_k": selected,
                    "selection_rate": float(selection_rate),
                    "mean_model_score": _safe_mean(bucket["model_scores"]),
                    "mean_embedding_cosine": _safe_mean(bucket["embedding_cosines"]),
                    "mean_years_experience": _safe_mean(bucket["years"]),
                    "positive_feedback": bucket["positive_feedback"],
                    "negative_feedback": bucket["negative_feedback"],
                    "positive_feedback_rate": (
                        float(positive_rate) if positive_rate is not None else None
                    ),
                }
            )

        group_metrics.sort(key=lambda g: g["selection_rate"], reverse=True)

        notes: list[str] = []
        reference_group: str | None = None
        dp_ratio: float | None = None
        eligible = [
            g for g in group_metrics
            if g["group_value"] != "unknown" and g["candidates_total"] >= 5
        ]
        if len(eligible) >= 2:
            best = max(eligible, key=lambda g: g["selection_rate"])
            worst = min(eligible, key=lambda g: g["selection_rate"])
            if best["selection_rate"] > 0:
                dp_ratio = worst["selection_rate"] / best["selection_rate"]
                reference_group = best["group_value"]
                if dp_ratio < 0.8:
                    notes.append(
                        f"Demographic parity ratio {dp_ratio:.2f} is below the 0.80 "
                        f"four-fifths threshold (worst='{worst['group_value']}', "
                        f"best='{best['group_value']}')."
                    )
        else:
            notes.append("Need at least two groups with >=5 candidates for parity ratio.")

        return {
            "group_by": group_by,
            "top_k_cutoff": int(top_k_cutoff),
            "total_candidates": sum(g["candidates_total"] for g in group_metrics),
            "total_runs": distinct_runs,
            "reference_group": reference_group,
            "demographic_parity_ratio": dp_ratio,
            "groups": group_metrics,
            "notes": notes,
        }


@lru_cache(maxsize=1)
def get_fairness_service() -> FairnessService:
    return FairnessService()
