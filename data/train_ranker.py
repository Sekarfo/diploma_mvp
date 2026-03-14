from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from sklearn.metrics import ndcg_score
from sklearn.model_selection import GroupKFold
from xgboost import XGBRanker

BASE_REQUIRED_COLUMNS = ["job_id", "resume_id", "manual_label"]

CORE_FEATURE_CANDIDATES = [
    "bm25_score",
    "normalized_bm25_score",
    "exact_skill_overlap_count",
    "exact_skill_overlap_ratio",
    "title_token_overlap_ratio",
    "years_experience_estimate",
    "semantic_similarity",
    "must_have_skill_coverage",
]

OPTIONAL_FEATURE_CANDIDATES = [
    "provisional_score",
]

DEFAULT_CSV_CANDIDATES = [
    Path("data/labels/labeled_pairs_first2000.csv"),
    
]

import pandas as pd


from pathlib import Path



def default_csv_path() -> str:
    for path in DEFAULT_CSV_CANDIDATES:
        if path.exists():
            return str(path)
    return str(DEFAULT_CSV_CANDIDATES[0])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train grouped XGBoost ranker for job-resume reranking.")
    parser.add_argument("--csv", default=default_csv_path(), help="Path to labeled CSV.")
    parser.add_argument("--model-out", default="ranker_model.json")
    parser.add_argument("--meta-out", default="ranker_metadata.json")
    parser.add_argument("--pred-out", default="cv_predictions.csv")
    parser.add_argument("--fold-metrics-out", default="fold_metrics.csv")
    parser.add_argument("--group-analysis-out", default="group_analysis.csv")
    parser.add_argument("--importance-out", default="feature_importance.csv")
    parser.add_argument("--n-splits", type=int, default=3)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--n-estimators", type=int, default=300)
    parser.add_argument("--learning-rate", type=float, default=0.05)
    parser.add_argument("--max-depth", type=int, default=4)
    parser.add_argument("--min-child-weight", type=float, default=2.0)
    parser.add_argument("--subsample", type=float, default=0.9)
    parser.add_argument("--colsample-bytree", type=float, default=0.9)
    parser.add_argument("--reg-lambda", type=float, default=2.0)
    parser.add_argument("--reg-alpha", type=float, default=0.0)
    parser.add_argument("--min-rows-per-job", type=int, default=5)
    parser.add_argument("--min-train-jobs", type=int, default=2)
    parser.add_argument("--relevance-threshold", type=int, default=1)
    parser.add_argument("--include-provisional-score", action="store_true")
    return parser.parse_args()


def load_csv(path: str) -> pd.DataFrame:
    print(f"Loading CSV: {path}")
    df = pd.read_csv(path, encoding="utf-8-sig")
    print(f"Raw loaded shape: {df.shape}")
    print(f"Columns: {list(df.columns)}")

    if "manual_label" not in df.columns:
        raise ValueError("CSV must contain 'manual_label' column.")

    raw = df["manual_label"].copy()

    df["manual_label"] = (
        df["manual_label"]
        .astype(str)
        .str.strip()
        .str.replace('"', "", regex=False)
        .str.replace("'", "", regex=False)
        .str.replace("\ufeff", "", regex=False)
        .str.lower()
    )

    label_map = {
        "0": 0,
        "1": 1,
        "0.0": 0,
        "1.0": 1,
        "false": 0,
        "true": 1,
        "no": 0,
        "yes": 1,
        "irrelevant": 0,
        "relevant": 1,
        "reject": 0,
        "accept": 1,
    }

    df["manual_label"] = df["manual_label"].replace(label_map)
    df["manual_label"] = pd.to_numeric(df["manual_label"], errors="coerce")

    print(f"Rows after manual_label numeric coercion: {df['manual_label'].notna().sum()} / {len(df)}")

    if df["manual_label"].notna().sum() == 0:
        print("Sample raw manual_label values:")
        print(raw.astype(str).head(20).tolist())
        print("Unique raw manual_label values:")
        print(raw.astype(str).str.strip().value_counts(dropna=False).head(20))
        raise ValueError("All rows were removed because manual_label could not be parsed.")

    df = df[df["manual_label"].isin([0, 1])].copy()

    if df.empty:
        raise ValueError("No valid rows left after filtering manual_label to {0,1}.")

    df["manual_label"] = df["manual_label"].astype(int)
    return df


def select_feature_columns(df: pd.DataFrame, include_provisional_score: bool) -> List[str]:
    features: List[str] = []

    for col in CORE_FEATURE_CANDIDATES:
        if col in df.columns:
            features.append(col)

    if include_provisional_score and "provisional_score" in df.columns:
        features.append("provisional_score")

    if len(features) < 3:
        raise ValueError(
            f"Too few usable feature columns found. Found: {features}. Need at least 3."
        )

    return features


def clean_and_impute_features(df: pd.DataFrame, feature_columns: List[str]) -> Tuple[pd.DataFrame, Dict[str, Dict[str, float]]]:
    df = df.copy()
    report: Dict[str, Dict[str, float]] = {}

    for col in feature_columns:
        original_non_null = df[col].notna().sum() if col in df.columns else 0

        df[col] = (
            df[col]
            .replace(["", " ", "None", "none", "NULL", "null", "N/A", "n/a", "unknown", "Unknown"], np.nan)
        )
        df[col] = pd.to_numeric(df[col], errors="coerce")

        non_null_after_numeric = int(df[col].notna().sum())
        null_count = int(df[col].isna().sum())

        if non_null_after_numeric == 0:
            print(f"Warning: column '{col}' is fully empty after numeric conversion. Filling with 0.")
            df[col] = 0.0
            fill_value = 0.0
        else:
            fill_value = float(df[col].median())
            df[col] = df[col].fillna(fill_value)

        report[col] = {
            "original_non_null": int(original_non_null),
            "non_null_after_numeric": non_null_after_numeric,
            "null_count_after_numeric": null_count,
            "fill_value": fill_value,
        }

    print(f"Rows after feature cleaning: {len(df)}")
    return df, report


def analyze_groups(df: pd.DataFrame, relevance_threshold: int) -> pd.DataFrame:
    def _count_relevant(s: pd.Series) -> int:
        return int((s >= relevance_threshold).sum())

    def _count_non_relevant(s: pd.Series) -> int:
        return int((s < relevance_threshold).sum())

    group_stats = (
        df.groupby("job_id")
        .agg(
            rows=("resume_id", "count"),
            unique_resumes=("resume_id", "nunique"),
            min_label=("manual_label", "min"),
            max_label=("manual_label", "max"),
            unique_labels=("manual_label", "nunique"),
            relevant_rows=("manual_label", _count_relevant),
            non_relevant_rows=("manual_label", _count_non_relevant),
        )
        .reset_index()
    )
    return group_stats.sort_values(["rows", "job_id"], ascending=[False, True]).reset_index(drop=True)


def filter_usable_groups(
    df: pd.DataFrame,
    group_stats: pd.DataFrame,
    min_rows_per_job: int,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    usable = group_stats[
        (group_stats["rows"] >= min_rows_per_job) &
        (group_stats["unique_labels"] >= 2) &
        (group_stats["relevant_rows"] > 0) &
        (group_stats["non_relevant_rows"] > 0)
    ].copy()

    usable_job_ids = set(usable["job_id"].tolist())
    filtered_df = df[df["job_id"].isin(usable_job_ids)].copy()
    return filtered_df, usable


def sort_for_ranking(df: pd.DataFrame) -> pd.DataFrame:
    return df.sort_values(["job_id", "resume_id"]).reset_index(drop=True)


def with_numeric_qid(df: pd.DataFrame) -> pd.DataFrame:
    out = sort_for_ranking(df).copy()
    out["qid_numeric"] = pd.factorize(out["job_id"], sort=True)[0].astype(np.uint32)
    return out


def build_xgb_ranker(args: argparse.Namespace) -> XGBRanker:
    return XGBRanker(
        objective="rank:ndcg",
        eval_metric="ndcg@10",
        learning_rate=args.learning_rate,
        n_estimators=args.n_estimators,
        max_depth=args.max_depth,
        min_child_weight=args.min_child_weight,
        subsample=args.subsample,
        colsample_bytree=args.colsample_bytree,
        reg_lambda=args.reg_lambda,
        reg_alpha=args.reg_alpha,
        random_state=args.random_state,
        tree_method="hist",
    )


def fit_ranker(
    train_df: pd.DataFrame,
    valid_df: pd.DataFrame,
    feature_columns: List[str],
    args: argparse.Namespace,
) -> XGBRanker:
    train_rank_df = with_numeric_qid(train_df)
    valid_rank_df = with_numeric_qid(valid_df)

    model = build_xgb_ranker(args)
    model.fit(
        train_rank_df[feature_columns],
        train_rank_df["manual_label"],
        qid=train_rank_df["qid_numeric"],
        eval_set=[(valid_rank_df[feature_columns], valid_rank_df["manual_label"])],
        eval_qid=[valid_rank_df["qid_numeric"]],
        verbose=False,
    )
    return model


def ndcg_at_k(y_true: np.ndarray, y_score: np.ndarray, k: int) -> float:
    if len(y_true) < 2:
        return float("nan")
    return float(ndcg_score([y_true], [y_score], k=min(k, len(y_true))))


def precision_at_k(y_true: np.ndarray, y_score: np.ndarray, k: int, relevance_threshold: int) -> float:
    order = np.argsort(-y_score)[: min(k, len(y_true))]
    if len(order) == 0:
        return float("nan")
    return float((y_true[order] >= relevance_threshold).sum() / len(order))


def recall_at_k(y_true: np.ndarray, y_score: np.ndarray, k: int, relevance_threshold: int) -> float:
    total_rel = int((y_true >= relevance_threshold).sum())
    if total_rel == 0:
        return float("nan")
    order = np.argsort(-y_score)[: min(k, len(y_true))]
    return float((y_true[order] >= relevance_threshold).sum() / total_rel)


def aggregate_group_metrics(df: pd.DataFrame, score_col: str, relevance_threshold: int) -> Dict[str, float]:
    rows = []

    for _, group in df.groupby("job_id"):
        y_true = group["manual_label"].to_numpy(dtype=float)
        y_score = group[score_col].to_numpy(dtype=float)

        rows.append({
            "ndcg@10": ndcg_at_k(y_true, y_score, 10),
            "precision@10": precision_at_k(y_true, y_score, 10, relevance_threshold),
            "recall@10": recall_at_k(y_true, y_score, 10, relevance_threshold),
        })

    g = pd.DataFrame(rows)
    return {
        "ndcg@10": float(g["ndcg@10"].mean()),
        "precision@10": float(g["precision@10"].mean()),
        "recall@10": float(g["recall@10"].mean()),
    }


def heuristic_score(df: pd.DataFrame, feature_columns: List[str]) -> np.ndarray:
    weights = {
        "normalized_bm25_score": 0.35,
        "bm25_score": 0.15,
        "exact_skill_overlap_ratio": 0.20,
        "exact_skill_overlap_count": 0.10,
        "title_token_overlap_ratio": 0.10,
        "years_experience_estimate": 0.10,
        "semantic_similarity": 0.20,
        "must_have_skill_coverage": 0.20,
        "provisional_score": 0.10,
    }

    used = {k: v for k, v in weights.items() if k in feature_columns}
    if not used:
        return np.zeros(len(df), dtype=float)

    weight_sum = sum(used.values())
    out = np.zeros(len(df), dtype=float)

    for col, w in used.items():
        x = df[col].to_numpy(dtype=float)
        xmin, xmax = np.min(x), np.max(x)
        if xmax > xmin:
            x = (x - xmin) / (xmax - xmin)
        else:
            x = np.zeros_like(x)
        out += (w / weight_sum) * x

    return out


def cross_validate(df: pd.DataFrame, feature_columns: List[str], args: argparse.Namespace) -> Tuple[pd.DataFrame, pd.DataFrame]:
    usable_jobs = df["job_id"].nunique()
    n_splits = min(args.n_splits, usable_jobs)

    if usable_jobs < 2:
        raise ValueError(
            f"Need at least 2 usable job groups for ranking. Found {usable_jobs}."
        )

    gkf = GroupKFold(n_splits=n_splits)
    X = df[feature_columns]
    y = df["manual_label"]
    groups = df["job_id"]

    pred_frames = []
    fold_rows = []

    for fold, (train_idx, valid_idx) in enumerate(gkf.split(X, y, groups), start=1):
        train_df = df.iloc[train_idx].copy()
        valid_df = df.iloc[valid_idx].copy()

        model = fit_ranker(train_df, valid_df, feature_columns, args)

        valid_df = sort_for_ranking(valid_df)
        valid_df["model_score"] = model.predict(valid_df[feature_columns])
        valid_df["baseline_score"] = heuristic_score(valid_df, feature_columns)
        valid_df["fold"] = fold

        model_metrics = aggregate_group_metrics(valid_df, "model_score", args.relevance_threshold)
        baseline_metrics = aggregate_group_metrics(valid_df, "baseline_score", args.relevance_threshold)

        fold_rows.append({
            "fold": fold,
            "rows": int(len(valid_df)),
            "jobs": int(valid_df["job_id"].nunique()),
            "model_ndcg@10": model_metrics["ndcg@10"],
            "model_precision@10": model_metrics["precision@10"],
            "model_recall@10": model_metrics["recall@10"],
            "baseline_ndcg@10": baseline_metrics["ndcg@10"],
            "baseline_precision@10": baseline_metrics["precision@10"],
            "baseline_recall@10": baseline_metrics["recall@10"],
        })

        pred_frames.append(valid_df[["job_id", "resume_id", "manual_label", "fold", "model_score", "baseline_score"]])

    return pd.concat(pred_frames, ignore_index=True), pd.DataFrame(fold_rows)


def train_final_model(df: pd.DataFrame, feature_columns: List[str], args: argparse.Namespace) -> XGBRanker:
    rank_df = with_numeric_qid(df)
    model = build_xgb_ranker(args)
    model.fit(rank_df[feature_columns], rank_df["manual_label"], qid=rank_df["qid_numeric"], verbose=False)
    return model


def save_feature_importance(model: XGBRanker, feature_columns: List[str], out_path: str) -> None:
    booster = model.get_booster()
    gain_scores = booster.get_score(importance_type="gain")

    rows = []
    for i, feature in enumerate(feature_columns):
        value = gain_scores.get(feature, gain_scores.get(f"f{i}", 0.0))
        rows.append({
            "feature": feature,
            "importance_gain": float(value),
        })

    pd.DataFrame(rows).sort_values("importance_gain", ascending=False).to_csv(out_path, index=False)


def main() -> None:
    args = parse_args()

    raw_df = load_csv(args.csv)
    feature_columns = select_feature_columns(raw_df, args.include_provisional_score)
    print(f"Selected features: {feature_columns}")

    raw_df, feature_clean_report = clean_and_impute_features(raw_df, feature_columns)

    print("Feature cleaning report:")
    print(json.dumps(feature_clean_report, indent=2))

    raw_group_stats = analyze_groups(raw_df, args.relevance_threshold)
    usable_df, usable_group_stats = filter_usable_groups(raw_df, raw_group_stats, args.min_rows_per_job)

    summary = {
        "raw_rows": int(len(raw_df)),
        "usable_rows": int(len(usable_df)),
        "raw_jobs": int(raw_df["job_id"].nunique()),
        "usable_jobs": int(usable_df["job_id"].nunique()),
        "raw_label_distribution": {str(k): int(v) for k, v in raw_df["manual_label"].value_counts().sort_index().items()},
        "usable_label_distribution": {str(k): int(v) for k, v in usable_df["manual_label"].value_counts().sort_index().items()},
        "jobs_with_only_one_label": int((raw_group_stats["unique_labels"] < 2).sum()),
    }

    print(json.dumps(summary, indent=2))

    raw_group_stats.to_csv(args.group_analysis_out, index=False)

    if usable_df.empty:
        print("No mixed-label job groups after strict filtering.")
        print("Falling back to relaxed training on all jobs with at least 2 rows.")
        relaxed_jobs = raw_group_stats[raw_group_stats["rows"] >= 2]["job_id"].tolist()
        usable_df = raw_df[raw_df["job_id"].isin(relaxed_jobs)].copy()

    if usable_df["job_id"].nunique() < 2:
        raise ValueError(
            "Still fewer than 2 job groups available for ranking. "
            "You must ensure at least 2 job_id groups with 2+ rows each."
        )

    predictions_df, fold_metrics_df = cross_validate(usable_df, feature_columns, args)

    predictions_df.to_csv(args.pred_out, index=False)
    fold_metrics_df.to_csv(args.fold_metrics_out, index=False)

    final_model = train_final_model(usable_df, feature_columns, args)
    final_model.save_model(args.model_out)
    save_feature_importance(final_model, feature_columns, args.importance_out)

    metadata = {
        "feature_columns": feature_columns,
        "feature_clean_report": feature_clean_report,
        "summary": summary,
        "fold_metrics_mean": fold_metrics_df.mean(numeric_only=True).to_dict(),
    }
    Path(args.meta_out).write_text(json.dumps(metadata, indent=2))

    print(f"Saved predictions to {args.pred_out}")
    print(f"Saved fold metrics to {args.fold_metrics_out}")
    print(f"Saved group analysis to {args.group_analysis_out}")
    print(f"Saved feature importance to {args.importance_out}")
    print(f"Saved model to {args.model_out}")
    print(f"Saved metadata to {args.meta_out}")


if __name__ == "__main__":
    main()