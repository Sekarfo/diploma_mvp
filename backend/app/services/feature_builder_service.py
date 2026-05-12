from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from backend.app.services.artifact_service import RuntimeArtifacts
from backend.app.services.errors import RankingError
from backend.app.services.runtime_utils import parse_list_col, title_overlap_ratio, to_float
from src.ml.features import engineer_features


class FeatureBuilderService:
    """Builds runtime ranker features that match training schema exactly.

    Cross-encoder is used only OFFLINE for label generation (data/generate_labels.py).
    Inference path is structured-features-only: ES retrieve -> LightGBM rank.
    """

    def build_features_for_hits(
        self,
        *,
        artifacts: RuntimeArtifacts,
        job_row: pd.Series,
        job_vector: np.ndarray,
        hits: list[dict[str, Any]],
        allow_elastic_score_fallback: bool = False,
    ) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        missing_resume_ids: list[str] = []

        job_id = str(job_row["job_id"])
        job_skills = set(parse_list_col(job_row.get("job_skills_norm", [])))
        job_years_required = to_float(job_row.get("job_years_required", 0.0), default=0.0)
        job_title = str(job_row.get("job_title", ""))

        for retrieval_rank, hit in enumerate(hits, start=1):
            src = hit.get("_source", {}) or {}
            resume_id = str(src.get("resume_id") or hit.get("_id") or "").strip()
            if not resume_id:
                continue

            resume_idx = artifacts.resume_index_by_id.get(resume_id)
            elastic_score = to_float(hit.get("retrieval_score_raw", hit.get("_score", 0.0)), default=0.0)
            embedding_source = "local_embedding"

            if resume_idx is None:
                missing_resume_ids.append(resume_id)
                if not allow_elastic_score_fallback:
                    continue

                embedding_cosine = elastic_score
                embedding_source = "elastic_score_fallback"
                resume_skills = set(parse_list_col(src.get("resume_skills_norm", [])))
                resume_titles = parse_list_col(src.get("resume_titles_norm", []))
                resume_years_experience = to_float(src.get("resume_years_experience", 0.0), default=0.0)
                resume_text = str(src.get("resume_text", "") or "")
            else:
                resume_row = artifacts.resumes_df.iloc[resume_idx]
                embedding_cosine = float(
                    np.dot(job_vector, artifacts.resume_embeddings[resume_idx])
                )
                resume_skills = set(parse_list_col(resume_row.get("resume_skills_norm", [])))
                resume_titles = parse_list_col(resume_row.get("resume_titles_norm", []))
                resume_years_experience = to_float(
                    resume_row.get("resume_years_experience", 0.0),
                    default=0.0,
                )
                resume_text = str(resume_row.get("resume_text", "") or "")

            skill_overlap_count = int(len(job_skills & resume_skills))
            skill_overlap_ratio = float(skill_overlap_count / max(len(job_skills), 1))
            years_gap = float(resume_years_experience - job_years_required)
            experience_match_flag = 1 if years_gap >= 0 else 0
            current_title_overlap = title_overlap_ratio(job_title, resume_titles)

            matched_skills = sorted(job_skills & resume_skills)
            missing_skills = sorted(job_skills - resume_skills)
            if experience_match_flag == 1:
                experience_summary = f"Meets required experience (+{years_gap:.2f} years)."
            else:
                experience_summary = f"Below required experience ({years_gap:.2f} years)."

            rows.append(
                {
                    "job_id": job_id,
                    "resume_id": resume_id,
                    "resume_text": resume_text,
                    "retrieval_rank": retrieval_rank,
                    "elastic_score": elastic_score,
                    "retrieval_score_raw": elastic_score,
                    "embedding_source": embedding_source,
                    "embedding_cosine": embedding_cosine,
                    "skill_overlap_count": skill_overlap_count,
                    "skill_overlap_ratio": skill_overlap_ratio,
                    "title_overlap_ratio": current_title_overlap,
                    "resume_years_experience": resume_years_experience,
                    "job_years_required": job_years_required,
                    "years_gap": years_gap,
                    "experience_match_flag": experience_match_flag,
                    "matched_skills": matched_skills[:10],
                    "missing_skills": missing_skills[:10],
                    "experience_summary": experience_summary,
                    "title_summary": f"Title overlap ratio {current_title_overlap:.2f}.",
                }
            )

        if missing_resume_ids and not allow_elastic_score_fallback:
            missing_preview = ", ".join(sorted(set(missing_resume_ids))[:10])
            raise RankingError(
                "Retrieved resume_ids missing in local embeddings. Reindex Elasticsearch from current artifacts "
                "or enable fallback mode. Missing ids sample: "
                f"{missing_preview}"
            )

        if not rows:
            return pd.DataFrame(rows)

        base_df = pd.DataFrame(rows)
        engineered_df = engineer_features(base_df)
        return engineered_df
