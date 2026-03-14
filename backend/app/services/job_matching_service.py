from __future__ import annotations

import pandas as pd

from backend.app.repositories import LocalCandidateRepository
from backend.app.services.feature_builder_service import FeatureBuilderService
from backend.app.services.ranking_service import RankingService


class JobMatchingService:
    """End-to-end MVP matcher: load local candidates -> build features -> rank."""

    def __init__(
        self,
        candidate_repository: LocalCandidateRepository | None = None,
        feature_builder: FeatureBuilderService | None = None,
        ranking_service: RankingService | None = None,
    ) -> None:
        self.candidate_repository = candidate_repository or LocalCandidateRepository()
        self.feature_builder = feature_builder or FeatureBuilderService()
        self.ranking_service = ranking_service or RankingService()

    def match_job(
        self,
        job_title: str,
        job_description: str,
        top_k: int = 10,
    ) -> tuple[pd.DataFrame, int]:
        if not job_title.strip():
            raise ValueError("job_title must not be empty.")
        if not job_description.strip():
            raise ValueError("job_description must not be empty.")
        if top_k <= 0:
            raise ValueError("top_k must be greater than 0.")

        candidates_df = self.candidate_repository.load_candidates()
        features_df = self.feature_builder.build_candidate_features(
            job_title=job_title,
            job_description=job_description,
            candidates_df=candidates_df,
        )
        features_df["baseline_score"] = self._compute_baseline_score(features_df)
        features_df["baseline_rank"] = self._rank_desc(features_df["baseline_score"])

        ranked_df = self.ranking_service.rank_candidates(features_df)
        ranked_df["model_rank"] = self._rank_desc(ranked_df["model_score"])
        ranked_df["explanation"] = ranked_df.apply(self._build_explanation, axis=1)
        ranked_df = ranked_df.sort_values("model_rank").reset_index(drop=True)
        ranked_df = self._select_output_columns(ranked_df)

        total_candidates = len(ranked_df)
        ranked_df = ranked_df.head(top_k).reset_index(drop=True)
        return ranked_df, total_candidates

    @staticmethod
    def _compute_baseline_score(df: pd.DataFrame) -> pd.Series:
        years_signal = (df["years_experience_estimate"].clip(lower=0) / 10.0).clip(upper=1.0)
        score = (
            0.55 * df["normalized_bm25_score"]
            + 0.25 * df["exact_skill_overlap_ratio"]
            + 0.15 * df["title_token_overlap_ratio"]
            + 0.05 * years_signal
        )
        return score.astype(float)

    @staticmethod
    def _rank_desc(values: pd.Series) -> pd.Series:
        return values.rank(method="first", ascending=False).astype(int)

    @staticmethod
    def _build_explanation(row: pd.Series) -> str:
        matched_skills = row.get("matched_skills", []) or []
        skill_preview = ", ".join(matched_skills[:3]) if matched_skills else "none"
        return (
            f"Matched skills: {skill_preview}; token overlap {row['exact_skill_overlap_count']:.0f}, "
            f"title overlap {row['title_token_overlap_ratio']:.2f}, "
            f"estimated experience {row['years_experience_estimate']:.1f} years."
        )

    @staticmethod
    def _select_output_columns(ranked_df: pd.DataFrame) -> pd.DataFrame:
        preferred = [
            "resume_id",
            "full_name",
            "headline",
            "baseline_score",
            "model_score",
            "baseline_rank",
            "model_rank",
            "matched_skills",
            "explanation",
            "bm25_score",
            "normalized_bm25_score",
            "exact_skill_overlap_count",
            "exact_skill_overlap_ratio",
            "title_token_overlap_ratio",
            "years_experience_estimate",
        ]
        available = [col for col in preferred if col in ranked_df.columns]
        return ranked_df[available].copy()
