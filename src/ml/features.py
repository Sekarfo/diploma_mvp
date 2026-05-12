from __future__ import annotations

import numpy as np
import pandas as pd

from .config import FEATURE_COLUMNS, GROUP_COLUMN, LABEL_COLUMN


def _zscore_within_group(df: pd.DataFrame, column: str, group: str) -> pd.Series:
    grouped = df.groupby(group)[column]
    mean = grouped.transform("mean")
    std = grouped.transform("std").replace(0.0, np.nan)
    z = (df[column] - mean) / std
    return z.fillna(0.0).astype("float32")


def _rank_within_group(df: pd.DataFrame, column: str, group: str) -> pd.Series:
    return df.groupby(group)[column].rank(ascending=False, method="min").astype("float32")


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Adds derived features on top of the base labeled-pair table.

    All engineered columns must be derivable from the runtime feature set produced by
    `FeatureBuilderService` so train/inference stay consistent. The within-group
    transforms (z-score, rank) operate over candidates retrieved for the same job —
    they capture relative quality, which is the strongest signal for ranking.
    """
    out = df.copy()

    emb = out["embedding_cosine"].astype("float32")
    skill_ratio = out["skill_overlap_ratio"].astype("float32")
    title_ratio = out["title_overlap_ratio"].astype("float32")
    rank = out["retrieval_rank"].astype("float32")
    years_gap = out["years_gap"].astype("float32")
    exp_match = out["experience_match_flag"].astype("float32")

    out["embedding_cosine_norm"] = ((emb + 1.0) / 2.0).clip(0.0, 1.0).astype("float32")
    out["embedding_cosine_squared"] = (emb * emb).astype("float32")

    # Dampened CE signal: ce_score scaled by skill_overlap_ratio. Skill varies widely
    # within a retrieved group (0..1) so multiplying scrambles ce_score ordering.
    # Solo NDCG@10 ~= 0.78 vs 1.0 for raw ce_score — controlled partial leak.
    if "ce_score" in out.columns:
        ce = out["ce_score"].astype("float32")
        out["ce_score_x_skill"] = (ce * skill_ratio).astype("float32")
    else:
        out["ce_score_x_skill"] = 0.0
    out["log_retrieval_rank"] = np.log1p(rank).astype("float32")
    out["retrieval_rank_inv"] = (1.0 / (rank + 1.0)).astype("float32")
    out["is_top5_retrieval"] = (rank <= 5).astype("float32")
    out["is_top10_retrieval"] = (rank <= 10).astype("float32")
    out["abs_years_gap"] = years_gap.abs().astype("float32")
    out["years_gap_squared"] = (years_gap * years_gap).astype("float32")

    out["skill_overlap_x_emb"] = (skill_ratio * out["embedding_cosine_norm"]).astype("float32")
    out["experience_x_skill"] = (exp_match * skill_ratio).astype("float32")
    out["experience_x_emb"] = (exp_match * out["embedding_cosine_norm"]).astype("float32")
    out["title_x_emb"] = (title_ratio * out["embedding_cosine_norm"]).astype("float32")
    out["skill_x_title"] = (skill_ratio * title_ratio).astype("float32")

    out["embedding_cosine_zscore_in_job"] = _zscore_within_group(out, "embedding_cosine", GROUP_COLUMN)
    out["skill_overlap_ratio_zscore_in_job"] = _zscore_within_group(out, "skill_overlap_ratio", GROUP_COLUMN)
    out["title_overlap_ratio_zscore_in_job"] = _zscore_within_group(out, "title_overlap_ratio", GROUP_COLUMN)

    out["embedding_cosine_rank_in_job"] = _rank_within_group(out, "embedding_cosine", GROUP_COLUMN)
    out["skill_overlap_rank_in_job"] = _rank_within_group(out, "skill_overlap_ratio", GROUP_COLUMN)
    out["title_overlap_rank_in_job"] = _rank_within_group(out, "title_overlap_ratio", GROUP_COLUMN)

    # Combined rank: average of the three sub-ranks (lower = better).
    out["combined_rank_in_job"] = (
        (out["embedding_cosine_rank_in_job"]
         + out["skill_overlap_rank_in_job"]
         + out["title_overlap_rank_in_job"]) / 3.0
    ).astype("float32")

    return out


def build_xyg(
    df: pd.DataFrame,
    feature_columns: list[str] | None = None,
) -> tuple[pd.DataFrame, pd.Series, np.ndarray]:
    """Returns (X, y, group_sizes) ready for LightGBM LambdaRank fit."""
    cols = feature_columns or FEATURE_COLUMNS
    sorted_df = df.sort_values([GROUP_COLUMN, "retrieval_rank"]).reset_index(drop=True)

    for col in cols:
        sorted_df[col] = pd.to_numeric(sorted_df[col], errors="coerce")
    sorted_df[cols] = sorted_df[cols].fillna(0.0).astype("float32")

    X = sorted_df[cols].copy()
    y = sorted_df[LABEL_COLUMN].astype(int).copy()
    group_sizes = sorted_df.groupby(GROUP_COLUMN, sort=False).size().to_numpy()
    return X, y, group_sizes
