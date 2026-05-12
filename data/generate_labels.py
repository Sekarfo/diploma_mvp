"""
Generate fine-grained relevance labels for (job, resume) pairs via a cross-encoder.

Input:
    pair_features_labeled.csv  (output of build_pairs.py, with feature columns)
    Clear/jobs_clean.csv       (raw job text)
    Clear/resumes_clean.csv    (raw resume text)

Output:
    pair_features_labeled.csv  (same file, with new 'ce_score' + 'final_label' columns,
                                filtered to keep only trainable jobs)

Labeling logic:
    1. Cross-encoder scores raw (job_text, resume_text) on a sigmoid scale [0, 1].
       This is a textual signal independent from the structured features used for training.

    2. Five absolute buckets (trainer uses label_gain = [0, 1, 3, 7, 15]):
            ce_score >= 0.65   ->  label 4  (strong positive)
            ce_score >= 0.50   ->  label 3
            ce_score >= 0.35   ->  label 2
            ce_score >= 0.25   ->  label 1
            ce_score <  0.25   ->  label 0  (irrelevant)

    3. Trainable filter: keep jobs that have BOTH a positive (label >= 3) AND a
       negative (label <= 1). LambdaRank needs label variation per group to learn.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from scipy.special import expit
from sentence_transformers import CrossEncoder


BASE_DIR = Path(__file__).resolve().parent
PAIR_CSV = BASE_DIR / "pair_features_labeled.csv"
JOBS_CSV = BASE_DIR / "Clear" / "jobs_clean.csv"
RESUMES_CSV = BASE_DIR / "Clear" / "resumes_clean.csv"

DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-12-v2"
DEFAULT_BATCH_SIZE = 64
DEFAULT_MAX_LENGTH = 512

# Fine-grained absolute thresholds on sigmoid(score) in [0, 1].
# Tuples are (lower_inclusive, upper_exclusive, label).
DEFAULT_LABEL_THRESHOLDS = (
    (0.00, 0.25, 0),
    (0.25, 0.35, 1),
    (0.35, 0.50, 2),
    (0.50, 0.65, 3),
    (0.65, 1.01, 4),
)

# Trainable filter: jobs must have at least one example on each side of the spectrum.
POSITIVE_LABELS = {3, 4}
NEGATIVE_LABELS = {0, 1}

DROP_LEGACY_COLUMNS = ["weak_score"]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Cross-encoder relabel of candidate pairs (5-bucket).")
    p.add_argument("--model", default=DEFAULT_MODEL,
                   help=f"CrossEncoder model. Default: {DEFAULT_MODEL}. "
                        "Use 'BAAI/bge-reranker-v2-m3' for multilingual / higher quality.")
    p.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    p.add_argument("--max-length", type=int, default=DEFAULT_MAX_LENGTH)
    p.add_argument("--device", default=None, help="cuda / cuda:0 / cpu. Auto-detect if omitted.")
    p.add_argument("--force-sigmoid", action="store_true")
    p.add_argument("--no-sigmoid", action="store_true")
    p.add_argument("--keep-degenerate", action="store_true",
                   help="Skip the trainable-jobs filter and keep all rows.")
    p.add_argument("--rescore", action="store_true",
                   help="Re-run the cross-encoder even if ce_score is already present.")
    return p.parse_args()


def _build_text_lookup(csv_path: Path, id_col: str, text_col: str, rename_to: str | None = None) -> dict[str, str]:
    df = pd.read_csv(csv_path, usecols=[id_col, text_col])
    df[id_col] = df[id_col].astype(str)
    df[text_col] = df[text_col].fillna("").astype(str)
    key_col = rename_to or id_col
    if rename_to:
        df = df.rename(columns={id_col: rename_to})
    return dict(zip(df[key_col], df[text_col]))


def _apply_sigmoid(raw_scores: np.ndarray, *, force: bool, never: bool) -> np.ndarray:
    if never:
        return raw_scores
    if force:
        return expit(raw_scores)
    if raw_scores.min() < -0.01 or raw_scores.max() > 1.01:
        return expit(raw_scores)
    return raw_scores


def _assign_labels(ce_probs: np.ndarray, thresholds=DEFAULT_LABEL_THRESHOLDS) -> np.ndarray:
    labels = np.full(len(ce_probs), -1, dtype=int)
    for low, high, lbl in thresholds:
        mask = (ce_probs >= low) & (ce_probs < high)
        labels[mask] = lbl
    labels[labels < 0] = 0
    return labels


def _print_distribution(label_series: pd.Series, title: str) -> None:
    total = max(len(label_series), 1)
    print(f"\n--- {title} ---")
    counts = label_series.value_counts().sort_index()
    for label, n in counts.items():
        pct = 100 * n / total
        print(f"  label {label}: {n:>7,}  ({pct:5.1f}%)")


def _score_pairs(model: CrossEncoder, pair_texts: list[list[str]], batch_size: int) -> np.ndarray:
    raw = model.predict(
        pair_texts,
        batch_size=batch_size,
        show_progress_bar=True,
        convert_to_numpy=True,
    )
    return np.asarray(raw, dtype=np.float64)


def main() -> None:
    args = parse_args()

    print(f"Loading {PAIR_CSV}...")
    pairs = pd.read_csv(PAIR_CSV)
    pairs["job_id"] = pairs["job_id"].astype(str)
    pairs["resume_id"] = pairs["resume_id"].astype(str)
    print(f"  pairs: {len(pairs):,}")

    if (
        not args.rescore
        and "ce_score" in pairs.columns
        and pairs["ce_score"].notna().all()
    ):
        print("ce_score already present in CSV — reusing existing scores. "
              "Pass --rescore to recompute via cross-encoder.")
        ce_probs = pairs["ce_score"].to_numpy(dtype=np.float64)
        raw_scores = pairs.get("ce_score_raw", pairs["ce_score"]).to_numpy(dtype=np.float64)
    else:
        job_text_by_id = _build_text_lookup(JOBS_CSV, "job_id", "job_text")
        resume_text_by_id = _build_text_lookup(RESUMES_CSV, "person_id", "resume_text", rename_to="resume_id")
        print(f"  job_text lookup: {len(job_text_by_id):,}")
        print(f"  resume_text lookup: {len(resume_text_by_id):,}")

        print("Building pair texts...")
        pair_texts: list[list[str]] = []
        missing_pairs = 0
        for job_id, resume_id in zip(pairs["job_id"].to_numpy(), pairs["resume_id"].to_numpy()):
            jt = job_text_by_id.get(job_id, "")
            rt = resume_text_by_id.get(resume_id, "")
            if not jt or not rt:
                missing_pairs += 1
            pair_texts.append([jt, rt])
        if missing_pairs:
            print(f"  warning: {missing_pairs:,} pairs have missing text on one side")

        device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
        print(f"Loading cross-encoder model={args.model} device={device} max_length={args.max_length}")
        model = CrossEncoder(args.model, max_length=args.max_length, device=device)

        print(f"Scoring {len(pair_texts):,} pairs (batch={args.batch_size})...")
        raw_scores = _score_pairs(model, pair_texts, args.batch_size)
        ce_probs = _apply_sigmoid(raw_scores, force=args.force_sigmoid, never=args.no_sigmoid)

    print(f"  raw score range: [{raw_scores.min():.3f}, {raw_scores.max():.3f}] "
          f"mean={raw_scores.mean():.3f}")
    print(f"  prob range:      [{ce_probs.min():.3f}, {ce_probs.max():.3f}] "
          f"mean={ce_probs.mean():.3f} median={np.median(ce_probs):.3f}")

    labels = _assign_labels(ce_probs)

    for col in DROP_LEGACY_COLUMNS:
        if col in pairs.columns:
            pairs = pairs.drop(columns=col)

    pairs["ce_score_raw"] = raw_scores.astype(np.float32).round(4)
    pairs["ce_score"] = ce_probs.astype(np.float32).round(4)
    pairs["final_label"] = labels.astype(int)
    pairs["within_job_rank"] = (
        pairs.groupby("job_id")["ce_score"].rank(method="first", ascending=False).astype(int)
    )

    _print_distribution(pairs["final_label"], "label distribution BEFORE degenerate filter")

    per_job = pairs.groupby("job_id")["final_label"].agg(["min", "max", "nunique"])
    print("\n--- degenerate jobs analysis ---")
    print(f"  total jobs:                            {len(per_job):>5,}")
    print(f"  no positive (max <= 2):                {(per_job['max'] <= 2).sum():>5,}")
    print(f"  no negative (min >= 2):                {(per_job['min'] >= 2).sum():>5,}")
    print(f"  single label per job (nunique == 1):   {(per_job['nunique'] == 1).sum():>5,}")

    trainable_mask = (per_job["max"] >= 3) & (per_job["min"] <= 1)
    trainable_jobs = per_job[trainable_mask].index
    print(f"  trainable (pos AND neg present):       {len(trainable_jobs):>5,}")

    if args.keep_degenerate:
        filtered = pairs
        print("\n[--keep-degenerate] keeping all rows.")
    else:
        filtered = pairs[pairs["job_id"].isin(trainable_jobs)].copy().reset_index(drop=True)
        print(f"  rows after filter: {len(filtered):,} "
              f"({100 * len(filtered) / max(len(pairs), 1):.1f}% of original)")

    _print_distribution(filtered["final_label"], "label distribution AFTER filter")

    print("\n--- ce_score distribution (filtered set) ---")
    print(filtered["ce_score"].describe(percentiles=[0.1, 0.25, 0.5, 0.75, 0.9]).round(4).to_string())

    print("\n--- per-job label spread (filtered set) ---")
    spread = filtered.groupby("job_id")["final_label"].agg(["min", "max", "mean", "nunique"])
    print(spread.describe().round(2).to_string())

    filtered.to_csv(PAIR_CSV, index=False)
    print(f"\nSaved -> {PAIR_CSV} ({len(filtered):,} rows, {filtered['job_id'].nunique():,} jobs)")

    print("\n--- example: 3 random jobs ---")
    rng = np.random.default_rng(seed=42)
    sample_ids = rng.choice(filtered["job_id"].unique(), size=min(3, filtered["job_id"].nunique()), replace=False)
    for jid in sample_ids:
        sub = filtered[filtered["job_id"] == jid].sort_values("within_job_rank")
        print(f"\njob_id={jid}")
        print(
            sub[[
                "within_job_rank",
                "ce_score",
                "embedding_cosine",
                "skill_overlap_count",
                "title_overlap_ratio",
                "final_label",
            ]]
            .head(10)
            .to_string(index=False)
        )


if __name__ == "__main__":
    main()
