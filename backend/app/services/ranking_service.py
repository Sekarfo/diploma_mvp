from __future__ import annotations

import logging

import lightgbm as lgb
import numpy as np
import pandas as pd

from backend.app.services.errors import RankingError

logger = logging.getLogger(__name__)


class RankingService:
    """Applies trained LightGBM LGBMRanker and returns score-sorted candidates."""

    def rank_candidates(
        self,
        *,
        candidates_df: pd.DataFrame,
        model: lgb.LGBMRanker,
        feature_columns: list[str],
    ) -> pd.DataFrame:
        if candidates_df.empty:
            raise RankingError("No candidates available for ranking.")

        missing_columns = [col for col in feature_columns if col not in candidates_df.columns]
        if missing_columns:
            raise RankingError(
                "Missing required runtime feature columns: " + ", ".join(missing_columns)
            )

        features_df = candidates_df[feature_columns].copy()
        for col in feature_columns:
            features_df[col] = pd.to_numeric(features_df[col], errors="coerce")
        features_df = features_df.fillna(0.0).astype("float32")

        try:
            scores = model.predict(features_df).astype(float)
        except Exception as exc:
            raise RankingError(f"LightGBM ranker prediction failed: {exc}") from exc

        ranked_df = candidates_df.copy()
        ranked_df["reranker_score_raw"] = scores
        ranked_df["model_score"] = ranked_df["reranker_score_raw"]
        self._attach_tree_shap_contributions(
            ranked_df=ranked_df,
            features_df=features_df,
            model=model,
            feature_columns=feature_columns,
        )
        ranked_df = ranked_df.sort_values("model_score", ascending=False).reset_index(drop=True)
        ranked_df["final_rank"] = (ranked_df.index + 1).astype(int)
        return ranked_df

    @staticmethod
    def _attach_tree_shap_contributions(
        *,
        ranked_df: pd.DataFrame,
        features_df: pd.DataFrame,
        model: lgb.LGBMRanker,
        feature_columns: list[str],
    ) -> None:
        default_base = (
            float(np.nanmean(ranked_df["model_score"].to_numpy(dtype=float)))
            if len(ranked_df)
            else 0.0
        )
        for feature in feature_columns:
            ranked_df[f"shap_{feature}"] = 0.0
        ranked_df["shap_base_value"] = default_base

        try:
            booster = model.booster_
            contribs = booster.predict(
                features_df.to_numpy(dtype=float),
                pred_contrib=True,
            )
            if contribs.ndim != 2 or contribs.shape[1] != len(feature_columns) + 1:
                raise RankingError(
                    "Unexpected pred_contrib shape: "
                    f"{contribs.shape}, expected (*, {len(feature_columns) + 1})"
                )
            for idx, feature in enumerate(feature_columns):
                ranked_df[f"shap_{feature}"] = contribs[:, idx].astype(float)
            ranked_df["shap_base_value"] = contribs[:, -1].astype(float)
        except RankingError:
            raise
        except Exception as exc:
            logger.warning("SHAP contribution computation failed (%s); zero-filled fallback used.", exc)
            return
