"""Active-learning loop: re-train LightGBM ranker on original labels + recruiter feedback.

Reads `recruiter_feedback` joined with `shortlist_candidates.feature_snapshot` from
Postgres, maps decisions to the 5-bucket `final_label` scheme used at train time,
merges with the original `pair_features_labeled.csv`, and trains a new model.

Run:
    python -m src.ml.retrain_with_feedback \
        --min-feedback 20 \
        --output models/lgbm_ranker_with_feedback.joblib

The new model is NOT swapped into production automatically — verify metrics first,
then point `models/lgbm_ranker.joblib` at the new artifact (or set a new symlink).

Decision → label mapping (matches LABEL_GAIN = [0, 1, 2, 4, 8]):
    reject     -> 0  (gain 0, "irrelevant")
    maybe      -> 2  (gain 2, "lukewarm")
    accept     -> 3  (gain 4, "good")
    interview  -> 4  (gain 8, "excellent")
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd

try:
    import psycopg
except ImportError as exc:
    raise SystemExit(
        "psycopg is required for retraining. Install with: pip install 'psycopg[binary]'"
    ) from exc

from .config import (
    EVAL_AT,
    FEATURE_COLUMNS,
    FEATURES_PATH,
    GROUP_COLUMN,
    LABEL_COLUMN,
    LABEL_GAIN,
    LABELED_PAIRS_CSV,
    METADATA_PATH,
    MODEL_PATH,
    MODELS_DIR,
    RANDOM_SEED,
)
from .features import build_xyg, engineer_features

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


DECISION_TO_LABEL = {
    "reject": 0,
    "maybe": 2,
    "accept": 3,
    "interview": 4,
}

# Median CE-score for feedback rows — original training data had real ce_score per pair,
# we don't store it in feature_snapshot. Using 0.5 keeps ce_score_x_skill in mid-range
# and prevents the model from learning "ce_score==0 means feedback origin" leakage.
_FEEDBACK_CE_DEFAULT = 0.5

_REQUIRED_SNAPSHOT_KEYS = (
    "embedding_cosine",
    "skill_overlap_count",
    "skill_overlap_ratio",
    "title_overlap_ratio",
    "years_gap",
    "experience_match_flag",
    "resume_years_experience",
    "job_years_required",
)


def load_feedback_pairs(database_url: str) -> pd.DataFrame:
    query = """
        SELECT
            r.id::text             AS run_id,
            r.existing_job_id      AS existing_job_id,
            r.vacancy_id::text     AS vacancy_id,
            c.id                   AS candidate_id,
            c.resume_id            AS resume_id,
            c.final_rank           AS retrieval_rank,
            c.feature_snapshot     AS feature_snapshot,
            f.decision             AS decision,
            f.rating               AS rating,
            f.created_at           AS feedback_at
        FROM recruiter_feedback f
        JOIN shortlist_candidates c ON c.id = f.candidate_id
        JOIN shortlist_runs r       ON r.id = f.run_id
        WHERE f.decision IN ('reject', 'maybe', 'accept', 'interview')
    """
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
            colnames = [d.name for d in cur.description]

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=colnames)

    # Group key for LambdaRank: prefer existing_job_id, fall back to vacancy_id, then run_id.
    df["job_id"] = (
        df["existing_job_id"].astype(str).replace({"None": ""})
        .where(lambda s: s.str.len() > 0, df["vacancy_id"].astype(str).replace({"None": ""}))
        .where(lambda s: s.str.len() > 0, df["run_id"].astype(str))
    )

    # Explode feature_snapshot JSON into columns.
    def _snap(row):
        v = row.get("feature_snapshot")
        if isinstance(v, dict):
            return v
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return {}
        return {}

    snapshots = df.apply(_snap, axis=1)
    for key in _REQUIRED_SNAPSHOT_KEYS:
        df[key] = snapshots.map(lambda d, k=key: d.get(k))

    df[LABEL_COLUMN] = df["decision"].map(DECISION_TO_LABEL).astype("Int64")
    df = df.dropna(subset=[LABEL_COLUMN] + list(_REQUIRED_SNAPSHOT_KEYS)).copy()
    df[LABEL_COLUMN] = df[LABEL_COLUMN].astype(int)

    df["ce_score"] = _FEEDBACK_CE_DEFAULT
    df["retrieval_rank"] = df["retrieval_rank"].fillna(0).astype(int)
    df["origin"] = "feedback"
    return df[
        [
            "job_id", "resume_id", "retrieval_rank", "ce_score",
            *list(_REQUIRED_SNAPSHOT_KEYS), LABEL_COLUMN, "origin",
        ]
    ]


def merge_with_original(feedback_df: pd.DataFrame, original_csv: Path) -> pd.DataFrame:
    original = pd.read_csv(original_csv)
    original = original.dropna(subset=[GROUP_COLUMN, LABEL_COLUMN, "resume_id"]).copy()
    original[LABEL_COLUMN] = original[LABEL_COLUMN].astype(int)
    original["origin"] = "teacher"

    # Drop overlap so feedback labels win for identical (job_id, resume_id).
    feedback_keys = set(zip(feedback_df["job_id"].astype(str), feedback_df["resume_id"].astype(str)))
    if feedback_keys:
        keys = original.apply(lambda r: (str(r["job_id"]), str(r["resume_id"])), axis=1)
        mask = keys.isin(feedback_keys)
        dropped = int(mask.sum())
        if dropped > 0:
            logger.info("Replacing %s teacher-labeled rows with feedback labels.", dropped)
        original = original.loc[~mask].copy()

    combined = pd.concat([original, feedback_df], ignore_index=True, sort=False)
    return combined


def train_model(df: pd.DataFrame, *, n_estimators: int, sample_weight_feedback: float) -> tuple[lgb.LGBMRanker, dict]:
    df = engineer_features(df)
    df = df.sort_values([GROUP_COLUMN, "retrieval_rank"]).reset_index(drop=True)

    weights = np.where(df["origin"] == "feedback", float(sample_weight_feedback), 1.0)
    X, y, group_sizes = build_xyg(df, FEATURE_COLUMNS)

    # Light hyperparameters — full sweep lives in src/ml/train.py. This retrain is a
    # warm-update on the existing schedule, so we use the known-good defaults.
    params = {
        "objective": "lambdarank",
        "metric": "ndcg",
        "ndcg_eval_at": list(EVAL_AT),
        "label_gain": list(LABEL_GAIN),
        "boosting_type": "gbdt",
        "verbosity": -1,
        "n_jobs": -1,
        "seed": RANDOM_SEED,
        "num_leaves": 31,
        "learning_rate": 0.02,
        "min_data_in_leaf": 40,
        "feature_fraction": 0.9,
        "bagging_fraction": 0.9,
        "bagging_freq": 3,
    }

    model = lgb.LGBMRanker(n_estimators=n_estimators, **params)
    model.fit(
        X, y,
        group=group_sizes,
        sample_weight=weights,
        callbacks=[lgb.log_evaluation(period=0)],
    )
    return model, params


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Retrain LightGBM ranker with recruiter feedback.")
    parser.add_argument("--database-url", type=str, default=os.getenv("DATABASE_URL", ""))
    parser.add_argument("--original-csv", type=Path, default=LABELED_PAIRS_CSV)
    parser.add_argument("--output", type=Path, default=None, help="Path for new model artifact (default: timestamped)")
    parser.add_argument("--n-estimators", type=int, default=2000)
    parser.add_argument(
        "--feedback-weight", type=float, default=4.0,
        help="LightGBM sample_weight multiplier for feedback rows vs teacher rows",
    )
    parser.add_argument(
        "--min-feedback", type=int, default=20,
        help="Refuse to retrain if fewer than this many feedback rows are available",
    )
    parser.add_argument(
        "--promote", action="store_true",
        help="After training, overwrite models/lgbm_ranker.joblib with the new model",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.database_url:
        raise SystemExit("DATABASE_URL must be set (env var or --database-url).")

    logger.info("Loading recruiter feedback from %s", args.database_url.split("@")[-1])
    feedback_df = load_feedback_pairs(args.database_url)
    logger.info("Loaded %s usable feedback rows", len(feedback_df))
    if len(feedback_df) < args.min_feedback:
        logger.warning(
            "Only %s feedback rows (< --min-feedback=%s); aborting.",
            len(feedback_df), args.min_feedback,
        )
        sys.exit(2)
    logger.info("Feedback label distribution: %s", feedback_df[LABEL_COLUMN].value_counts().sort_index().to_dict())

    combined = merge_with_original(feedback_df, args.original_csv)
    logger.info(
        "Combined dataset: rows=%s jobs=%s (feedback=%s teacher=%s)",
        len(combined),
        combined[GROUP_COLUMN].nunique(),
        int((combined["origin"] == "feedback").sum()),
        int((combined["origin"] == "teacher").sum()),
    )

    model, params = train_model(
        combined,
        n_estimators=args.n_estimators,
        sample_weight_feedback=args.feedback_weight,
    )

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = args.output or MODELS_DIR / f"lgbm_ranker_feedback_{timestamp}.joblib"
    joblib.dump(model, out_path)
    joblib.dump(FEATURE_COLUMNS, FEATURES_PATH)
    logger.info("Saved retrained model to %s", out_path)

    metadata = {
        "trained_at": timestamp,
        "origin": "active_learning_retrain",
        "feedback_rows": int((combined["origin"] == "feedback").sum()),
        "teacher_rows": int((combined["origin"] == "teacher").sum()),
        "feedback_weight": float(args.feedback_weight),
        "label_distribution": combined[LABEL_COLUMN].value_counts().sort_index().to_dict(),
        "params": params,
        "n_estimators": int(args.n_estimators),
        "feature_columns": list(FEATURE_COLUMNS),
    }
    metadata_path = out_path.with_suffix(".meta.json")
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Saved metadata to %s", metadata_path)

    if args.promote:
        joblib.dump(model, MODEL_PATH)
        meta_path = MODEL_PATH.with_suffix(".meta.json")
        meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        # Clear the in-process artifact cache so backend reload picks the new model up.
        METADATA_PATH.write_text(
            json.dumps({"promoted_from": str(out_path), **metadata}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("Promoted retrained model into %s (restart backend to apply).", MODEL_PATH)


if __name__ == "__main__":
    main()
