from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd
from sklearn.metrics import ndcg_score

from .config import EVAL_AT, GROUP_COLUMN, LABEL_COLUMN


def _ndcg_at_k(group: pd.DataFrame, k: int) -> float | None:
    if group[LABEL_COLUMN].nunique() < 2:
        return None
    true_relevance = group[LABEL_COLUMN].to_numpy().reshape(1, -1).astype(float)
    pred_scores = group["pred"].to_numpy().reshape(1, -1).astype(float)
    return float(ndcg_score(true_relevance, pred_scores, k=k))


def _precision_recall_at_k(group: pd.DataFrame, k: int) -> tuple[float, float]:
    sorted_group = group.sort_values("pred", ascending=False)
    top_k = sorted_group.head(k)
    relevant_in_top = int((top_k[LABEL_COLUMN] >= 1).sum())
    total_relevant = int((group[LABEL_COLUMN] >= 1).sum())
    precision = relevant_in_top / max(k, 1)
    recall = relevant_in_top / total_relevant if total_relevant else 0.0
    return precision, recall


def _average_precision(group: pd.DataFrame) -> float:
    sorted_group = group.sort_values("pred", ascending=False).reset_index(drop=True)
    relevances = (sorted_group[LABEL_COLUMN] >= 1).astype(int).to_numpy()
    if relevances.sum() == 0:
        return 0.0
    cumulative_hits = np.cumsum(relevances)
    ranks = np.arange(1, len(relevances) + 1)
    precision_at_hits = cumulative_hits / ranks
    return float(np.sum(precision_at_hits * relevances) / relevances.sum())


def _reciprocal_rank(group: pd.DataFrame) -> float:
    sorted_group = group.sort_values("pred", ascending=False).reset_index(drop=True)
    hits = np.flatnonzero((sorted_group[LABEL_COLUMN] >= 1).to_numpy())
    if hits.size == 0:
        return 0.0
    return float(1.0 / (hits[0] + 1))


def evaluate_predictions(
    df: pd.DataFrame,
    pred_column: str = "pred",
    ks: Iterable[int] | None = None,
) -> dict[str, float]:
    """Computes ranking metrics aggregated over query groups.

    The frame must already contain `final_label`, `pred`, and `job_id`.
    """
    ks_list = list(ks or EVAL_AT)
    working = df.copy()
    working["pred"] = working[pred_column].astype(float)

    ndcg_by_k: dict[int, list[float]] = {k: [] for k in ks_list}
    precision_by_k: dict[int, list[float]] = {k: [] for k in ks_list}
    recall_by_k: dict[int, list[float]] = {k: [] for k in ks_list}
    ap_per_group: list[float] = []
    rr_per_group: list[float] = []

    for _, group in working.groupby(GROUP_COLUMN, sort=False):
        for k in ks_list:
            value = _ndcg_at_k(group, k)
            if value is not None:
                ndcg_by_k[k].append(value)
            precision, recall = _precision_recall_at_k(group, k)
            precision_by_k[k].append(precision)
            recall_by_k[k].append(recall)
        ap_per_group.append(_average_precision(group))
        rr_per_group.append(_reciprocal_rank(group))

    metrics: dict[str, float] = {}
    for k in ks_list:
        metrics[f"ndcg@{k}"] = float(np.mean(ndcg_by_k[k])) if ndcg_by_k[k] else 0.0
        metrics[f"precision@{k}"] = float(np.mean(precision_by_k[k])) if precision_by_k[k] else 0.0
        metrics[f"recall@{k}"] = float(np.mean(recall_by_k[k])) if recall_by_k[k] else 0.0
    metrics["map"] = float(np.mean(ap_per_group)) if ap_per_group else 0.0
    metrics["mrr"] = float(np.mean(rr_per_group)) if rr_per_group else 0.0
    metrics["num_query_groups"] = int(working[GROUP_COLUMN].nunique())
    metrics["num_rows"] = int(len(working))
    return metrics


def per_job_metrics(df: pd.DataFrame, pred_column: str = "pred") -> pd.DataFrame:
    rows = []
    working = df.copy()
    working["pred"] = working[pred_column].astype(float)
    for job_id, group in working.groupby(GROUP_COLUMN, sort=False):
        row: dict[str, float | str] = {"job_id": str(job_id), "rows": int(len(group))}
        for k in EVAL_AT:
            ndcg_value = _ndcg_at_k(group, k)
            row[f"ndcg@{k}"] = float(ndcg_value) if ndcg_value is not None else float("nan")
            precision, recall = _precision_recall_at_k(group, k)
            row[f"precision@{k}"] = float(precision)
            row[f"recall@{k}"] = float(recall)
        row["map"] = _average_precision(group)
        row["mrr"] = _reciprocal_rank(group)
        rows.append(row)
    return pd.DataFrame(rows)
