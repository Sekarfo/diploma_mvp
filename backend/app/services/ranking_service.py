from __future__ import annotations

from pathlib import Path
from typing import Sequence

import pandas as pd
from xgboost import XGBRanker

from backend.app.config.ranking import FEATURE_COLUMNS, RANKER_MODEL_PATH


class RankingService:
    """Inference service for scoring and ranking job-resume candidates."""

    def __init__(
        self,
        model_path: str | Path = RANKER_MODEL_PATH,
        feature_columns: Sequence[str] = FEATURE_COLUMNS,
    ) -> None:
        self.model_path = Path(model_path)
        self.feature_columns = list(feature_columns)
        self._model = self._load_model()

    def _load_model(self) -> XGBRanker:
        if not self.model_path.exists():
            raise FileNotFoundError(f"Ranker model not found: {self.model_path}")

        model = XGBRanker()
        model.load_model(self.model_path)
        return model

    def rank_candidates(self, candidates_df: pd.DataFrame) -> pd.DataFrame:
        if not isinstance(candidates_df, pd.DataFrame):
            raise TypeError("candidates_df must be a pandas DataFrame.")
        if candidates_df.empty:
            raise ValueError("candidates_df is empty. Provide at least one candidate row.")

        missing_columns = [col for col in self.feature_columns if col not in candidates_df.columns]
        if missing_columns:
            raise ValueError(
                "Missing required feature columns: " + ", ".join(missing_columns)
            )

        features_df = candidates_df[self.feature_columns].copy()
        for col in self.feature_columns:
            features_df[col] = pd.to_numeric(features_df[col], errors="coerce")

        invalid_columns = features_df.columns[features_df.isna().any()].tolist()
        if invalid_columns:
            raise ValueError(
                "Feature columns contain non-numeric or missing values: "
                + ", ".join(invalid_columns)
            )

        scores = self._model.predict(features_df)

        ranked_df = candidates_df.copy()
        ranked_df["model_score"] = scores.astype(float)
        ranked_df = ranked_df.sort_values("model_score", ascending=False).reset_index(drop=True)
        return ranked_df

