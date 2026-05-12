from __future__ import annotations

import logging
import re
from pathlib import Path

import numpy as np
import pandas as pd

from backend.app.config import Settings, get_settings
from backend.app.services.artifact_service import ArtifactService
from backend.app.services.elasticsearch_service import ElasticsearchRetrievalService
from backend.app.services.errors import EmptyRetrievalError, JobNotFoundError
from backend.app.services.explanation_service import ExplanationService
from backend.app.services.feature_builder_service import FeatureBuilderService
from backend.app.services.ranking_service import RankingService
from backend.app.services.runtime_utils import parse_list_col, token_set, to_float

logger = logging.getLogger(__name__)
YEARS_PATTERN = re.compile(r"\b(\d{1,2})\+?\s*(?:years?|yrs?)\b", re.IGNORECASE)


class ShortlistService:
    """End-to-end runtime service: retrieve -> build features -> rank -> explain."""
    FUSION_ALPHA = 0.3
    FUSION_BETA = 0.7

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        artifact_service: ArtifactService | None = None,
        retrieval_service: ElasticsearchRetrievalService | None = None,
        feature_builder: FeatureBuilderService | None = None,
        ranking_service: RankingService | None = None,
        explanation_service: ExplanationService | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.artifact_service = artifact_service or ArtifactService(self.settings)
        self.retrieval_service = retrieval_service or ElasticsearchRetrievalService(self.settings)
        self.feature_builder = feature_builder or FeatureBuilderService()
        self.ranking_service = ranking_service or RankingService()
        self.explanation_service = explanation_service or ExplanationService()

    def list_jobs(self) -> list[dict]:
        artifacts = self.artifact_service.get_artifacts()
        jobs_df = artifacts.jobs_df

        results: list[dict] = []
        for _, row in jobs_df.iterrows():
            description = str(row.get("job_description", ""))
            preview = description[:220].strip()
            if len(description) > 220:
                preview += "..."

            results.append(
                {
                    "job_id": str(row["job_id"]),
                    "job_title": str(row.get("job_title", "")),
                    "job_years_required": float(row.get("job_years_required", 0.0)),
                    "description_preview": preview,
                    "job_skills_norm": list(row.get("job_skills_norm", []) or []),
                }
            )
        return results

    def get_job(self, job_id: str) -> dict:
        artifacts = self.artifact_service.get_artifacts()
        job_row, _ = self._get_job_row(job_id=job_id, artifacts=artifacts)
        return {
            "job_id": str(job_row["job_id"]),
            "job_title": str(job_row.get("job_title", "")),
            "job_description": str(job_row.get("job_description", "")),
            "job_years_required": float(job_row.get("job_years_required", 0.0)),
            "job_skills_norm": list(job_row.get("job_skills_norm", []) or []),
        }

    def get_stats(self) -> dict:
        artifacts = self.artifact_service.get_artifacts()
        return {
            "total_jobs": int(len(artifacts.jobs_df)),
            "total_resumes": int(len(artifacts.resumes_df)),
        }

    def shortlist_for_vacancy(
        self,
        *,
        vacancy_title: str,
        vacancy_description: str,
        top_k: int | None = None,
        num_candidates: int | None = None,
        job_years_required: float | None = None,
        job_skills_norm: list[str] | None = None,
        index_name: str | None = None,
        retrieved_csv: Path | None = None,
        allow_elastic_score_fallback: bool = False,
    ) -> dict:
        artifacts = self.artifact_service.get_artifacts()
        top_k_value, num_candidates_value = self._resolve_limits(top_k, num_candidates)

        normalized_title = str(vacancy_title).strip()
        normalized_description = str(vacancy_description).strip()
        if not normalized_title:
            raise ValueError("vacancy_title must not be empty")
        if not normalized_description:
            raise ValueError("vacancy_description must not be empty")

        derived_skills = self._derive_vacancy_skills(
            artifacts=artifacts,
            vacancy_title=normalized_title,
            vacancy_description=normalized_description,
            explicit_skills=job_skills_norm,
        )
        derived_years_required = (
            to_float(job_years_required, default=0.0)
            if job_years_required is not None
            else self._derive_years_required(normalized_title, normalized_description)
        )

        proxy_job_row, proxy_job_idx = self._select_proxy_job(
            artifacts=artifacts,
            vacancy_title=normalized_title,
            vacancy_description=normalized_description,
            vacancy_skills=derived_skills,
        )
        query_vector = artifacts.job_embeddings[proxy_job_idx]

        vacancy_job_row = pd.Series(
            {
                "job_id": "ad_hoc_vacancy",
                "job_title": normalized_title,
                "job_description": normalized_description,
                "job_skills_norm": derived_skills,
                "job_years_required": derived_years_required,
            }
        )

        result = self._run_shortlist_pipeline(
            artifacts=artifacts,
            job_row=vacancy_job_row,
            query_vector=query_vector,
            top_k_value=top_k_value,
            num_candidates_value=num_candidates_value,
            index_name=index_name,
            retrieved_csv=retrieved_csv,
            allow_elastic_score_fallback=allow_elastic_score_fallback,
        )
        result["proxy_job_id"] = str(proxy_job_row["job_id"])
        return result

    def shortlist(
        self,
        *,
        job_id: str,
        top_k: int | None = None,
        num_candidates: int | None = None,
        index_name: str | None = None,
        retrieved_csv: Path | None = None,
        allow_elastic_score_fallback: bool = False,
    ) -> dict:
        artifacts = self.artifact_service.get_artifacts()
        job_row, job_idx = self._get_job_row(job_id=job_id, artifacts=artifacts)
        query_vector = artifacts.job_embeddings[job_idx]

        top_k_value, num_candidates_value = self._resolve_limits(top_k, num_candidates)
        return self._run_shortlist_pipeline(
            artifacts=artifacts,
            job_row=job_row,
            query_vector=query_vector,
            top_k_value=top_k_value,
            num_candidates_value=num_candidates_value,
            index_name=index_name,
            retrieved_csv=retrieved_csv,
            allow_elastic_score_fallback=allow_elastic_score_fallback,
        )

    def _run_shortlist_pipeline(
        self,
        *,
        artifacts,
        job_row: pd.Series,
        query_vector: np.ndarray,
        top_k_value: int,
        num_candidates_value: int,
        index_name: str | None,
        retrieved_csv: Path | None,
        allow_elastic_score_fallback: bool,
    ) -> dict:
        logger.info(
            "Shortlist request start job_id=%s top_k=%s num_candidates=%s",
            str(job_row.get("job_id", "")),
            top_k_value,
            num_candidates_value,
        )
        total_available_candidates = int(len(artifacts.resumes_df))
        effective_top_k = min(top_k_value, total_available_candidates)
        requested_pool_size = max(num_candidates_value, top_k_value)
        effective_pool_size = min(requested_pool_size, total_available_candidates)
        ann_num_candidates = effective_pool_size

        if requested_pool_size > total_available_candidates:
            logger.info(
                (
                    "Requested candidate pool=%s exceeds available resumes=%s. "
                    "Using effective_pool=%s."
                ),
                requested_pool_size,
                total_available_candidates,
                effective_pool_size,
            )

        logger.info(
            (
                "Retrieval configuration: requested_pool=%s, effective_pool=%s "
                "(rerank pool), ann_num_candidates=%s"
            ),
            requested_pool_size,
            effective_pool_size,
            ann_num_candidates,
        )

        if retrieved_csv is not None:
            hits = self.retrieval_service.retrieve_hits_from_csv(retrieved_csv, top_k=effective_pool_size)
        else:
            job_text = " ".join(
                str(job_row.get(field, "") or "")
                for field in ("job_title", "job_description")
            ).strip()
            job_skills_list = parse_list_col(job_row.get("job_skills_norm", []))
            hits = self.retrieval_service.retrieve_hits(
                query_vector=query_vector,
                top_k=effective_pool_size,
                num_candidates=ann_num_candidates,
                index_name=index_name,
                query_text=job_text,
                query_skills=job_skills_list,
                query_title=str(job_row.get("job_title", "") or ""),
            )

        if not hits:
            raise EmptyRetrievalError(f"No candidates retrieved for job_id={job_row.get('job_id', '')}")
        logger.info("Retrieved %s candidates from retrieval layer (before rerank truncation)", len(hits))

        features_df = self.feature_builder.build_features_for_hits(
            artifacts=artifacts,
            job_row=job_row,
            job_vector=query_vector,
            hits=hits,
            allow_elastic_score_fallback=allow_elastic_score_fallback,
        )
        if features_df.empty:
            raise EmptyRetrievalError(
                f"No usable candidates left after feature build for job_id={job_row.get('job_id', '')}"
            )

        ranked_df = self.ranking_service.rank_candidates(
            candidates_df=features_df,
            model=artifacts.model,
            feature_columns=artifacts.feature_columns,
        )
        logger.info("Ranked %s candidates (reranker raw order)", len(ranked_df))

        fused_df = self._apply_fusion_scores(ranked_df)
        logger.info("Computed fused scoring for %s candidates", len(fused_df))

        final_df = fused_df.head(effective_top_k).copy().reset_index(drop=True)
        final_df["final_rank"] = np.arange(1, len(final_df) + 1, dtype=int)
        candidates = self._to_candidate_records(final_df)
        logger.info("Returning top %s fused candidates out of %s reranked candidates", len(candidates), len(fused_df))

        return {
            "job_id": str(job_row["job_id"]),
            "job_title": str(job_row.get("job_title", "")),
            "total_candidates": len(candidates),
            "retrieved_count": len(hits),
            "top_k": effective_top_k,
            "num_candidates": effective_pool_size,
            "requested_top_k": top_k_value,
            "requested_num_candidates": num_candidates_value,
            "max_available_candidates": total_available_candidates,
            "candidates": candidates,
        }

    def _derive_vacancy_skills(
        self,
        *,
        artifacts,
        vacancy_title: str,
        vacancy_description: str,
        explicit_skills: list[str] | None,
    ) -> list[str]:
        if explicit_skills:
            cleaned = sorted({skill.strip().lower() for skill in explicit_skills if str(skill).strip()})
            if cleaned:
                return cleaned

        vocabulary: set[str] = set()
        for skills in artifacts.jobs_df["job_skills_norm"].tolist():
            vocabulary.update(parse_list_col(skills))
        vocabulary = {str(skill).strip().lower() for skill in vocabulary if str(skill).strip()}

        text = f"{vacancy_title} {vacancy_description}".lower()
        matched = [skill for skill in vocabulary if skill in text]
        if matched:
            return sorted(set(matched))

        fallback_tokens = [token for token in token_set(vacancy_title) if len(token) > 2]
        return sorted(set(fallback_tokens[:10]))

    @staticmethod
    def _derive_years_required(vacancy_title: str, vacancy_description: str) -> float:
        text = f"{vacancy_title} {vacancy_description}"
        matches = YEARS_PATTERN.findall(text)
        values = [float(int(m)) for m in matches if 0 <= int(m) <= 60]
        return max(values) if values else 0.0

    def _select_proxy_job(
        self,
        *,
        artifacts,
        vacancy_title: str,
        vacancy_description: str,
        vacancy_skills: list[str],
    ) -> tuple[pd.Series, int]:
        vacancy_tokens = token_set(f"{vacancy_title} {vacancy_description}")
        vacancy_skills_set = set(vacancy_skills)
        vacancy_title_tokens = token_set(vacancy_title)

        best_idx = 0
        best_score = -1.0
        jobs_df = artifacts.jobs_df

        for idx, row in jobs_df.iterrows():
            row_skills = set(parse_list_col(row.get("job_skills_norm", [])))
            row_title_tokens = token_set(str(row.get("job_title", "")))
            row_text_tokens = token_set(str(row.get("job_description", "")))

            skill_overlap = (
                len(vacancy_skills_set & row_skills) / max(len(vacancy_skills_set), 1)
                if vacancy_skills_set
                else 0.0
            )
            title_overlap = (
                len(vacancy_title_tokens & row_title_tokens) / max(len(vacancy_title_tokens), 1)
                if vacancy_title_tokens
                else 0.0
            )
            text_overlap = (
                len(vacancy_tokens & row_text_tokens) / max(len(vacancy_tokens), 1)
                if vacancy_tokens
                else 0.0
            )

            score = 0.55 * skill_overlap + 0.25 * title_overlap + 0.20 * text_overlap
            if score > best_score:
                best_score = score
                best_idx = int(idx)

        return jobs_df.iloc[best_idx], best_idx

    def _to_candidate_records(self, ranked_df: pd.DataFrame) -> list[dict]:
        records: list[dict] = []
        for _, row in ranked_df.iterrows():
            explanation = self.explanation_service.build_explanation(row)
            records.append(
                {
                    "final_rank": int(row["final_rank"]),
                    "resume_id": str(row["resume_id"]),
                    "resume_text": str(row.get("resume_text", "") or ""),
                    "model_score": float(row["model_score"]),
                    "score": float(row["score"]),
                    "score_label": str(row["score_label"]),
                    "retrieval_rank": int(row["retrieval_rank"]),
                    "retrieval_score_raw": float(row["retrieval_score_raw"]),
                    "retrieval_score_norm": float(row["retrieval_score_norm"]),
                    "reranker_score_raw": float(row["reranker_score_raw"]),
                    "reranker_score_norm": float(row["reranker_score_norm"]),
                    "fusion_alpha": float(row["fusion_alpha"]),
                    "fusion_beta": float(row["fusion_beta"]),
                    "retrieval_contribution": float(row["retrieval_contribution"]),
                    "reranker_contribution": float(row["reranker_contribution"]),
                    "final_fusion_score": float(row["final_fusion_score"]),
                    "embedding_cosine": float(row["embedding_cosine"]),
                    "skill_overlap_count": int(row["skill_overlap_count"]),
                    "skill_overlap_ratio": float(row["skill_overlap_ratio"]),
                    "title_overlap_ratio": float(row["title_overlap_ratio"]),
                    "resume_years_experience": float(row["resume_years_experience"]),
                    "job_years_required": float(row["job_years_required"]),
                    "years_gap": float(row["years_gap"]),
                    "experience_match_flag": int(row["experience_match_flag"]),
                    "explanation": explanation,
                }
            )
        return records

    @staticmethod
    def minmax_normalize(values: list[float]) -> list[float]:
        if not values:
            return []
        numeric = np.asarray(values, dtype=float)
        min_value = float(np.min(numeric))
        max_value = float(np.max(numeric))
        if max_value == min_value:
            return [1.0] * len(values)
        normalized = (numeric - min_value) / (max_value - min_value)
        return [float(np.clip(item, 0.0, 1.0)) for item in normalized.tolist()]

    def _apply_fusion_scores(self, ranked_df: pd.DataFrame) -> pd.DataFrame:
        fused_df = ranked_df.copy()
        fused_df["retrieval_score_raw"] = pd.to_numeric(
            fused_df.get("retrieval_score_raw", fused_df.get("elastic_score")),
            errors="coerce",
        )
        fused_df["reranker_score_raw"] = pd.to_numeric(fused_df.get("model_score"), errors="coerce")

        missing_mask = fused_df["retrieval_score_raw"].isna() | fused_df["reranker_score_raw"].isna()
        dropped_count = int(missing_mask.sum())
        if dropped_count > 0:
            logger.warning(
                "Dropping %s candidates from fused ranking due to missing retrieval/reranker raw score.",
                dropped_count,
            )
            fused_df = fused_df.loc[~missing_mask].copy()

        if fused_df.empty:
            raise EmptyRetrievalError("No candidates left for fusion scoring after score validation.")

        retrieval_values = fused_df["retrieval_score_raw"].astype(float).tolist()
        reranker_values = fused_df["reranker_score_raw"].astype(float).tolist()

        fused_df["retrieval_score_norm"] = self.minmax_normalize(retrieval_values)
        fused_df["reranker_score_norm"] = self.minmax_normalize(reranker_values)

        fused_df["fusion_alpha"] = float(self.FUSION_ALPHA)
        fused_df["fusion_beta"] = float(self.FUSION_BETA)
        fused_df["retrieval_contribution"] = fused_df["fusion_alpha"] * fused_df["retrieval_score_norm"]
        fused_df["reranker_contribution"] = fused_df["fusion_beta"] * fused_df["reranker_score_norm"]

        # NOTE: reranker features already contain retrieval-related evidence (e.g., retrieval_rank / semantic similarity).
        # This fusion intentionally keeps that potential double-counting for transparency and backward compatibility.
        fused_df["final_fusion_score"] = fused_df["retrieval_contribution"] + fused_df["reranker_contribution"]
        fused_df["score"] = fused_df["final_fusion_score"]
        fused_df["score_label"] = "fused_relevance"

        logger.info(
            (
                "Fusion stats candidates=%s retrieval_raw[min=%.6f max=%.6f] "
                "reranker_raw[min=%.6f max=%.6f] alpha=%.2f beta=%.2f"
            ),
            len(fused_df),
            float(np.min(retrieval_values)),
            float(np.max(retrieval_values)),
            float(np.min(reranker_values)),
            float(np.max(reranker_values)),
            float(self.FUSION_ALPHA),
            float(self.FUSION_BETA),
        )

        fused_df = fused_df.sort_values(
            by=["final_fusion_score", "reranker_score_norm", "retrieval_score_norm", "resume_id"],
            ascending=[False, False, False, True],
        ).reset_index(drop=True)
        fused_df["final_rank"] = np.arange(1, len(fused_df) + 1, dtype=int)
        return fused_df

    def _resolve_limits(self, top_k: int | None, num_candidates: int | None) -> tuple[int, int]:
        resolved_top_k = top_k or self.settings.default_top_k
        resolved_num_candidates = num_candidates or self.settings.default_num_candidates

        if resolved_top_k <= 0:
            raise ValueError("top_k must be greater than 0")
        if resolved_num_candidates <= 0:
            raise ValueError("num_candidates must be greater than 0")
        if resolved_top_k > self.settings.max_top_k:
            raise ValueError(f"top_k exceeds max allowed {self.settings.max_top_k}")
        if resolved_num_candidates > self.settings.max_num_candidates:
            raise ValueError(f"num_candidates exceeds max allowed {self.settings.max_num_candidates}")

        if resolved_num_candidates < resolved_top_k:
            resolved_num_candidates = resolved_top_k

        return int(resolved_top_k), int(resolved_num_candidates)

    @staticmethod
    def _get_job_row(job_id: str, artifacts) -> tuple[pd.Series, int]:
        normalized_job_id = str(job_id).strip()
        if not normalized_job_id:
            raise ValueError("job_id must not be empty")

        job_idx = artifacts.job_index_by_id.get(normalized_job_id)
        if job_idx is None:
            raise JobNotFoundError(f"job_id not found: {normalized_job_id}")

        job_row = artifacts.jobs_df.iloc[job_idx]
        return job_row, job_idx
