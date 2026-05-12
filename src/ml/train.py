from __future__ import annotations

import argparse
import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit

from .config import (
    EVAL_AT,
    FEATURE_COLUMNS,
    FEATURES_PATH,
    GLOBAL_SHAP_PATH,
    GROUP_COLUMN,
    LABEL_COLUMN,
    LABEL_GAIN,
    LABELED_PAIRS_CSV,
    METADATA_PATH,
    METRICS_DIR,
    MODEL_PATH,
    MODELS_DIR,
    RANDOM_SEED,
    SUMMARY_JSON_PATH,
    TEST_SIZE,
    VALID_SIZE,
    VALIDATION_PRED_PATH,
)
from .evaluate import evaluate_predictions, per_job_metrics
from .features import build_xyg, engineer_features

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


@dataclass
class TrainResult:
    best_params: dict
    valid_metrics: dict[str, float]
    test_metrics: dict[str, float]
    feature_importance: list[dict]
    best_iteration: int
    total_trials: int


def _group_split(
    df: pd.DataFrame,
    test_size: float,
    seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    splitter = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=seed)
    train_idx, test_idx = next(splitter.split(df, groups=df[GROUP_COLUMN]))
    return df.iloc[train_idx].reset_index(drop=True), df.iloc[test_idx].reset_index(drop=True)


def _sample_param_grid(rng: np.random.Generator) -> dict:
    # Slow-and-deep ranges. Previous run hit best_iteration=8 — the model was
    # underfitting because LR was too aggressive for a noisy 62-group valid set.
    # Lower LR + bigger leaves count + smaller min_data lets trees actually grow.
    return {
        "num_leaves": int(rng.choice([15, 31, 47, 63])),
        "learning_rate": float(rng.choice([0.005, 0.01, 0.015, 0.02, 0.03])),
        "min_data_in_leaf": int(rng.choice([20, 40, 60, 80, 120])),
        "feature_fraction": float(rng.choice([0.7, 0.8, 0.9, 1.0])),
        "bagging_fraction": float(rng.choice([0.7, 0.8, 0.9, 1.0])),
        "bagging_freq": int(rng.choice([0, 3, 5])),
        "lambda_l1": float(rng.choice([0.0, 0.1, 0.5])),
        "lambda_l2": float(rng.choice([0.0, 0.5, 1.0])),
        "min_gain_to_split": float(rng.choice([0.0, 0.01, 0.05])),
        "max_depth": int(rng.choice([4, 6, 8, -1])),
    }


def _fixed_params() -> dict:
    return {
        "objective": "lambdarank",
        "metric": "ndcg",
        "ndcg_eval_at": list(EVAL_AT),
        "label_gain": list(LABEL_GAIN),
        "boosting_type": "gbdt",
        "verbosity": -1,
        "n_jobs": -1,
        "seed": RANDOM_SEED,
    }


def _fit_one(
    *,
    X_train: pd.DataFrame,
    y_train: pd.Series,
    group_train: np.ndarray,
    X_valid: pd.DataFrame,
    y_valid: pd.Series,
    group_valid: np.ndarray,
    params: dict,
    n_estimators: int,
    early_stopping_rounds: int,
) -> lgb.LGBMRanker:
    model = lgb.LGBMRanker(
        n_estimators=n_estimators,
        **{**_fixed_params(), **params},
    )
    callbacks = [
        lgb.early_stopping(stopping_rounds=early_stopping_rounds, verbose=False),
        lgb.log_evaluation(period=0),
    ]
    model.fit(
        X_train,
        y_train,
        group=group_train,
        eval_set=[(X_valid, y_valid)],
        eval_group=[group_valid],
        eval_at=list(EVAL_AT),
        callbacks=callbacks,
    )
    return model


def _score_model(
    model: lgb.LGBMRanker,
    X: pd.DataFrame,
    base_df: pd.DataFrame,
) -> dict[str, float]:
    pred = model.predict(X, num_iteration=model.best_iteration_)
    eval_df = base_df.copy()
    eval_df["pred"] = pred
    return evaluate_predictions(eval_df)


def random_search(
    *,
    train_df: pd.DataFrame,
    valid_df: pd.DataFrame,
    n_trials: int,
    n_estimators: int,
    early_stopping_rounds: int,
    seed: int,
) -> tuple[lgb.LGBMRanker, dict, list[dict]]:
    X_train, y_train, group_train = build_xyg(train_df, FEATURE_COLUMNS)
    X_valid, y_valid, group_valid = build_xyg(valid_df, FEATURE_COLUMNS)

    rng = np.random.default_rng(seed)
    trial_records: list[dict] = []

    best_model: lgb.LGBMRanker | None = None
    best_score = -np.inf
    best_params: dict = {}

    for trial_index in range(n_trials):
        params = _sample_param_grid(rng)
        started = time.perf_counter()
        try:
            model = _fit_one(
                X_train=X_train,
                y_train=y_train,
                group_train=group_train,
                X_valid=X_valid,
                y_valid=y_valid,
                group_valid=group_valid,
                params=params,
                n_estimators=n_estimators,
                early_stopping_rounds=early_stopping_rounds,
            )
        except Exception as exc:
            logger.warning("trial=%s failed params=%s err=%s", trial_index, params, exc)
            trial_records.append({"trial": trial_index, "params": params, "error": str(exc)})
            continue

        valid_metrics = _score_model(
            model,
            X_valid.sort_index(),
            valid_df.sort_values([GROUP_COLUMN, "retrieval_rank"]).reset_index(drop=True),
        )
        score = float(valid_metrics["ndcg@10"])
        elapsed = round(time.perf_counter() - started, 1)
        trial_records.append(
            {
                "trial": trial_index,
                "params": params,
                "best_iteration": int(model.best_iteration_ or 0),
                "ndcg@10": score,
                "ndcg@5": float(valid_metrics["ndcg@5"]),
                "ndcg@20": float(valid_metrics["ndcg@20"]),
                "map": float(valid_metrics["map"]),
                "elapsed_sec": elapsed,
            }
        )

        logger.info(
            "trial=%s ndcg@10=%.4f map=%.4f best_iter=%s elapsed=%ss params=%s",
            trial_index,
            score,
            valid_metrics["map"],
            int(model.best_iteration_ or 0),
            elapsed,
            params,
        )

        if score > best_score:
            best_score = score
            best_model = model
            best_params = params

    if best_model is None:
        raise RuntimeError("All training trials failed. Check data and parameter sampling.")

    return best_model, best_params, trial_records


def _global_shap_summary(model: lgb.LGBMRanker, X: pd.DataFrame, feature_columns: list[str]) -> pd.DataFrame:
    booster = model.booster_
    contribs = booster.predict(
        X.to_numpy(dtype=float),
        pred_contrib=True,
        num_iteration=model.best_iteration_,
    )
    if contribs.ndim != 2 or contribs.shape[1] != len(feature_columns) + 1:
        raise RuntimeError(
            f"Unexpected SHAP contributions shape: got {contribs.shape}, "
            f"expected (n_rows, {len(feature_columns) + 1})"
        )
    feature_contribs = contribs[:, : len(feature_columns)]
    rows = []
    for idx, feature in enumerate(feature_columns):
        column = feature_contribs[:, idx]
        rows.append(
            {
                "feature": feature,
                "mean_abs_shap": float(np.mean(np.abs(column))),
                "mean_shap": float(np.mean(column)),
                "std_shap": float(np.std(column)),
            }
        )
    summary = pd.DataFrame(rows).sort_values("mean_abs_shap", ascending=False).reset_index(drop=True)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train LightGBM LambdaRank reranker.")
    parser.add_argument("--input", type=Path, default=LABELED_PAIRS_CSV)
    parser.add_argument("--n-trials", type=int, default=40)
    parser.add_argument("--n-estimators", type=int, default=8000)
    parser.add_argument("--early-stopping", type=int, default=500)
    parser.add_argument("--seed", type=int, default=RANDOM_SEED)
    parser.add_argument("--test-size", type=float, default=TEST_SIZE)
    parser.add_argument("--valid-size", type=float, default=VALID_SIZE)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    METRICS_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("Loading labeled pairs from %s", args.input)
    df = pd.read_csv(args.input)
    df = df.dropna(subset=[GROUP_COLUMN, LABEL_COLUMN, "resume_id"]).copy()
    df[LABEL_COLUMN] = df[LABEL_COLUMN].astype(int)

    df = engineer_features(df)

    label_variety = df.groupby(GROUP_COLUMN)[LABEL_COLUMN].nunique()
    eligible_jobs = label_variety[label_variety >= 2].index
    df = df[df[GROUP_COLUMN].isin(eligible_jobs)].copy()
    if df.empty:
        raise RuntimeError("After filtering for label variety, no jobs remain. Check labeling.")

    logger.info(
        "Working set: rows=%s jobs=%s label_distribution=%s",
        len(df),
        df[GROUP_COLUMN].nunique(),
        df[LABEL_COLUMN].value_counts().sort_index().to_dict(),
    )

    train_valid_df, test_df = _group_split(df, args.test_size, args.seed)
    valid_split = args.valid_size / (1.0 - args.test_size)
    train_df, valid_df = _group_split(train_valid_df, valid_split, args.seed + 1)

    logger.info(
        "Splits: train_rows=%s valid_rows=%s test_rows=%s | train_jobs=%s valid_jobs=%s test_jobs=%s",
        len(train_df),
        len(valid_df),
        len(test_df),
        train_df[GROUP_COLUMN].nunique(),
        valid_df[GROUP_COLUMN].nunique(),
        test_df[GROUP_COLUMN].nunique(),
    )

    best_model, best_params, trial_records = random_search(
        train_df=train_df,
        valid_df=valid_df,
        n_trials=args.n_trials,
        n_estimators=args.n_estimators,
        early_stopping_rounds=args.early_stopping,
        seed=args.seed,
    )

    X_train, y_train, group_train = build_xyg(train_df, FEATURE_COLUMNS)
    X_valid, y_valid, group_valid = build_xyg(valid_df, FEATURE_COLUMNS)
    X_test, _, _ = build_xyg(test_df, FEATURE_COLUMNS)

    logger.info("Re-fitting best model on train+valid with best params: %s", best_params)
    combined_df = pd.concat([train_df, valid_df], ignore_index=True)
    X_combined, y_combined, group_combined = build_xyg(combined_df, FEATURE_COLUMNS)
    final_model = lgb.LGBMRanker(
        n_estimators=int(best_model.best_iteration_ or args.n_estimators),
        **{**_fixed_params(), **best_params},
    )
    final_model.fit(
        X_combined,
        y_combined,
        group=group_combined,
        eval_at=list(EVAL_AT),
        callbacks=[lgb.log_evaluation(period=0)],
    )

    valid_metrics = _score_model(
        best_model,
        X_valid,
        valid_df.sort_values([GROUP_COLUMN, "retrieval_rank"]).reset_index(drop=True),
    )

    test_df_sorted = test_df.sort_values([GROUP_COLUMN, "retrieval_rank"]).reset_index(drop=True)
    test_pred = final_model.predict(X_test)
    test_eval_df = test_df_sorted.copy()
    test_eval_df["pred"] = test_pred
    test_metrics = evaluate_predictions(test_eval_df)

    logger.info("Valid metrics: %s", {k: round(v, 4) for k, v in valid_metrics.items() if isinstance(v, float)})
    logger.info("Test  metrics: %s", {k: round(v, 4) for k, v in test_metrics.items() if isinstance(v, float)})

    joblib.dump(final_model, MODEL_PATH)
    joblib.dump(FEATURE_COLUMNS, FEATURES_PATH)
    logger.info("Saved model to %s", MODEL_PATH)
    logger.info("Saved feature list to %s", FEATURES_PATH)

    importance_split = final_model.booster_.feature_importance(importance_type="split")
    importance_gain = final_model.booster_.feature_importance(importance_type="gain")
    feature_importance_records = [
        {
            "feature": feature,
            "importance_split": int(importance_split[idx]),
            "importance_gain": float(importance_gain[idx]),
        }
        for idx, feature in enumerate(FEATURE_COLUMNS)
    ]
    feature_importance_records.sort(key=lambda item: item["importance_gain"], reverse=True)

    shap_summary = _global_shap_summary(final_model, X_test, FEATURE_COLUMNS)
    shap_summary.to_csv(GLOBAL_SHAP_PATH, index=False)
    logger.info("Saved SHAP global summary to %s", GLOBAL_SHAP_PATH)

    test_eval_df[["job_id", "resume_id", "final_label", "pred"]].to_csv(VALIDATION_PRED_PATH, index=False)
    logger.info("Saved validation predictions to %s", VALIDATION_PRED_PATH)

    per_job = per_job_metrics(test_eval_df)
    per_job.to_csv(METRICS_DIR / "per_job_metrics.csv", index=False)

    metadata = {
        "model_type": "lightgbm.LGBMRanker",
        "objective": "lambdarank",
        "metric": "ndcg",
        "ndcg_eval_at": list(EVAL_AT),
        "label_gain": list(LABEL_GAIN),
        "feature_columns": FEATURE_COLUMNS,
        "best_params": best_params,
        "best_iteration": int(final_model.best_iteration_ or final_model.n_estimators),
        "n_trials": args.n_trials,
        "train_rows": int(len(train_df)),
        "valid_rows": int(len(valid_df)),
        "test_rows": int(len(test_df)),
        "train_jobs": int(train_df[GROUP_COLUMN].nunique()),
        "valid_jobs": int(valid_df[GROUP_COLUMN].nunique()),
        "test_jobs": int(test_df[GROUP_COLUMN].nunique()),
        "label_distribution": df[LABEL_COLUMN].value_counts().sort_index().to_dict(),
        "feature_importance": feature_importance_records,
        "valid_metrics": valid_metrics,
        "test_metrics": test_metrics,
        "trials": trial_records,
    }
    METADATA_PATH.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    SUMMARY_JSON_PATH.write_text(
        json.dumps(
            {
                "model_path": str(MODEL_PATH),
                "features_path": str(FEATURES_PATH),
                "valid_metrics": valid_metrics,
                "test_metrics": test_metrics,
                "best_params": best_params,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    logger.info("Saved metadata to %s", METADATA_PATH)
    logger.info("Training complete.")


if __name__ == "__main__":
    main()
