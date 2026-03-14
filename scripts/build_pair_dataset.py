#!/usr/bin/env python3
"""
Build a BM25-based job-resume pair dataset for manual labeling.

Example:
python build_pair_dataset.py \
  --jobs jobs.jsonl \
  --resumes resumes.jsonl \
  --out pairs.csv \
  --review-out review_batch.csv \
  --top-k 100 \
  --seed 42
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import regex as re
from rank_bm25 import BM25Okapi


TOKEN_PATTERN = re.compile(r"c\+\+|c#|\.net|aws|gcp|azure|sql|[a-z0-9]+(?:[+#.][a-z0-9]+)*")
MULTISPACE_PATTERN = re.compile(r"\s+")
YEARS_RANGE_PATTERN = re.compile(r"\b(\d{1,2})\s*(?:-|to)\s*(\d{1,2})\s*(?:years?|yrs?)\b")
YEARS_SINGLE_PATTERN = re.compile(r"\b(\d{1,2})\+?\s*(?:years?|yrs?)\b")
DATE_RANGE_PATTERN = re.compile(r"\b((?:19|20)\d{2})\s*-\s*((?:19|20)\d{2})\b")

IMPORTANT_TOKENS = {"c++", "c#", ".net", "aws", "gcp", "azure", "sql", "python", "linux"}
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "to",
    "with",
    "will",
    "you",
    "your",
    "we",
    "our",
    "their",
    "this",
    "these",
    "those",
    "experience",
    "years",
    "year",
    "job",
    "role",
}

OUTPUT_COLUMNS = [
    "job_id",
    "resume_id",
    "job_title",
    "bm25_score",
    "normalized_bm25_score",
    "exact_skill_overlap_count",
    "exact_skill_overlap_ratio",
    "title_token_overlap_ratio",
    "years_experience_estimate",
    "provisional_score",
    "provisional_rank",
    "manual_label",
    "label_notes",
    "reviewer",
    "reviewed_at",
]


def load_jsonl(path: Path, kind: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            raw = line.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON in {path} at line {line_no}") from exc
            if not isinstance(obj, dict):
                continue

            item_id = str(obj.get("id", "")).strip()
            if not item_id:
                continue

            if kind == "jobs":
                title = str(obj.get("title", "") or "").strip()
                text_description = str(obj.get("text_description", "") or "").strip()
                rows.append(
                    {
                        "id": item_id,
                        "title": title,
                        "text_description": text_description,
                    }
                )
            elif kind == "resumes":
                text_description = str(obj.get("text_description", "") or "").strip()
                rows.append(
                    {
                        "id": item_id,
                        "text_description": text_description,
                    }
                )
            else:
                raise ValueError(f"Unsupported kind: {kind}")

    df = pd.DataFrame(rows)
    if df.empty:
        if kind == "jobs":
            return pd.DataFrame(columns=["id", "title", "text_description"])
        return pd.DataFrame(columns=["id", "text_description"])
    return df.drop_duplicates(subset=["id"], keep="first").reset_index(drop=True)


def normalize_text(text: Any) -> str:
    if text is None:
        return ""
    normalized = str(text).lower()
    normalized = MULTISPACE_PATTERN.sub(" ", normalized)
    return normalized.strip()


def tokenize(text: str) -> list[str]:
    normalized = normalize_text(text)
    return TOKEN_PATTERN.findall(normalized)


def build_bm25_index(tokenized_resumes: list[list[str]]) -> BM25Okapi:
    return BM25Okapi(tokenized_resumes)


def _extract_skill_tokens(tokens: list[str]) -> set[str]:
    skill_tokens: set[str] = set()
    for token in tokens:
        if token in IMPORTANT_TOKENS:
            skill_tokens.add(token)
            continue
        if token in STOPWORDS:
            continue
        if len(token) <= 2 and token not in {"js", "go", "ml", "ai"}:
            continue
        skill_tokens.add(token)
    return skill_tokens


def compute_overlap_features(
    job_tokens: list[str], resume_tokens: list[str], job_title_tokens: list[str]
) -> dict[str, float | int]:
    job_token_set = set(job_tokens)
    resume_token_set = set(resume_tokens)
    job_skill_tokens = _extract_skill_tokens(job_tokens)
    resume_skill_tokens = _extract_skill_tokens(resume_tokens)

    overlap = job_skill_tokens & resume_skill_tokens
    overlap_count = len(overlap)
    overlap_ratio = overlap_count / len(job_skill_tokens) if job_skill_tokens else 0.0

    title_set = {token for token in job_title_tokens if token not in STOPWORDS}
    title_overlap_ratio = len(title_set & resume_token_set) / len(title_set) if title_set else 0.0

    return {
        "exact_skill_overlap_count": overlap_count,
        "exact_skill_overlap_ratio": overlap_ratio,
        "title_token_overlap_ratio": title_overlap_ratio,
        "has_python": int("python" in resume_token_set),
        "has_aws": int("aws" in resume_token_set),
        "has_azure": int("azure" in resume_token_set),
        "has_linux": int("linux" in resume_token_set),
    }


def estimate_years_experience(text: str) -> float:
    normalized = normalize_text(text)
    estimates: list[float] = []

    for start, end in YEARS_RANGE_PATTERN.findall(normalized):
        low = int(start)
        high = int(end)
        if 0 <= low <= 50 and 0 <= high <= 50:
            estimates.append(float(max(low, high)))

    for years in YEARS_SINGLE_PATTERN.findall(normalized):
        value = int(years)
        if 0 <= value <= 50:
            estimates.append(float(value))

    for start, end in DATE_RANGE_PATTERN.findall(normalized):
        low = int(start)
        high = int(end)
        if 1900 <= low <= 2100 and 1900 <= high <= 2100 and high >= low:
            diff = high - low
            if 0 <= diff <= 50:
                estimates.append(float(diff))

    return max(estimates) if estimates else 0.0


def build_pairs_for_job(
    job_id: str,
    job_title: str,
    job_tokens: list[str],
    job_title_tokens: list[str],
    bm25_index: BM25Okapi,
    resume_ids: list[str],
    resume_tokens: list[list[str]],
    resume_years: np.ndarray,
    max_experience: float,
    top_k: int,
) -> list[dict[str, Any]]:
    bm25_scores = np.asarray(bm25_index.get_scores(job_tokens), dtype=float)
    if bm25_scores.size == 0:
        return []

    bm25_min = float(np.min(bm25_scores))
    bm25_max = float(np.max(bm25_scores))
    if bm25_max == bm25_min:
        normalized_scores = np.zeros_like(bm25_scores)
    else:
        normalized_scores = (bm25_scores - bm25_min) / (bm25_max - bm25_min)

    top_n = min(top_k, bm25_scores.size)
    top_indices = np.argsort(-bm25_scores, kind="mergesort")[:top_n]

    rows: list[dict[str, Any]] = []
    for idx in top_indices:
        resume_idx = int(idx)
        overlap = compute_overlap_features(
            job_tokens=job_tokens,
            resume_tokens=resume_tokens[resume_idx],
            job_title_tokens=job_title_tokens,
        )
        experience_years = float(resume_years[resume_idx])
        normalized_experience_signal = (
            min(1.0, experience_years / max_experience) if max_experience > 0 else 0.0
        )

        provisional_score = (
            0.70 * float(normalized_scores[resume_idx])
            + 0.15 * float(overlap["exact_skill_overlap_ratio"])
            + 0.10 * float(overlap["title_token_overlap_ratio"])
            + 0.05 * normalized_experience_signal
        )

        rows.append(
            {
                "job_id": job_id,
                "resume_id": resume_ids[resume_idx],
                "job_title": job_title,
                "bm25_score": float(bm25_scores[resume_idx]),
                "normalized_bm25_score": float(normalized_scores[resume_idx]),
                "exact_skill_overlap_count": int(overlap["exact_skill_overlap_count"]),
                "exact_skill_overlap_ratio": float(overlap["exact_skill_overlap_ratio"]),
                "title_token_overlap_ratio": float(overlap["title_token_overlap_ratio"]),
                "has_python": int(overlap["has_python"]),
                "has_aws": int(overlap["has_aws"]),
                "has_azure": int(overlap["has_azure"]),
                "has_linux": int(overlap["has_linux"]),
                "years_experience_estimate": experience_years,
                "normalized_experience_signal": normalized_experience_signal,
                "provisional_score": provisional_score,
                "manual_label": "",
                "label_notes": "",
                "reviewer": "",
                "reviewed_at": "",
            }
        )

    rows.sort(
        key=lambda row: (
            -float(row["provisional_score"]),
            -float(row["normalized_bm25_score"]),
            -float(row["bm25_score"]),
            str(row["resume_id"]),
        )
    )

    for rank, row in enumerate(rows, start=1):
        row["provisional_rank"] = rank

    return rows


def sample_review_batch(pairs_df: pd.DataFrame, seed: int, top_k: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    max_random_rank = min(100, top_k)
    sampled_groups: list[pd.DataFrame] = []

    for _, group in pairs_df.groupby("job_id", sort=False):
        ordered = group.sort_values("provisional_rank", kind="mergesort")
        top_20 = ordered[ordered["provisional_rank"] <= 20]
        ranks_21_30 = ordered[
            (ordered["provisional_rank"] >= 21) & (ordered["provisional_rank"] <= 30)
        ]
        random_pool = ordered[
            (ordered["provisional_rank"] >= 31) & (ordered["provisional_rank"] <= max_random_rank)
        ]

        if random_pool.empty:
            random_samples = random_pool
        else:
            sample_n = min(10, len(random_pool))
            chosen_idx = rng.choice(random_pool.index.to_numpy(), size=sample_n, replace=False)
            random_samples = random_pool.loc[chosen_idx]

        selected = pd.concat([top_20, ranks_21_30, random_samples], ignore_index=False)
        selected = selected.drop_duplicates(subset=["job_id", "resume_id"], keep="first")
        selected = selected.sort_values("provisional_rank", kind="mergesort")
        sampled_groups.append(selected)

    if not sampled_groups:
        return pairs_df.iloc[0:0].copy()

    review_df = pd.concat(sampled_groups, ignore_index=True)
    return review_df.reset_index(drop=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build BM25 pair datasets for manual labeling.")
    parser.add_argument("--jobs", type=Path, required=True, help="Path to jobs.jsonl")
    parser.add_argument("--resumes", type=Path, required=True, help="Path to resumes.jsonl")
    parser.add_argument("--out", type=Path, required=True, help="Output pairs CSV path")
    parser.add_argument(
        "--review-out",
        type=Path,
        required=True,
        help="Output review batch CSV path",
    )
    parser.add_argument("--top-k", type=int, default=100, help="Top resumes per job")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for deterministic sampling")
    args = parser.parse_args()

    if args.top_k <= 0:
        raise ValueError("--top-k must be > 0")
    return args


def main() -> None:
    args = parse_args()

    jobs_df = load_jsonl(args.jobs, kind="jobs")
    resumes_df = load_jsonl(args.resumes, kind="resumes")

    if jobs_df.empty:
        raise ValueError("No jobs loaded from jobs JSONL.")
    if resumes_df.empty:
        raise ValueError("No resumes loaded from resumes JSONL.")

    jobs_df["title_raw"] = jobs_df["title"].fillna("").astype(str).str.strip()
    jobs_df["title_norm"] = jobs_df["title_raw"].map(normalize_text)
    jobs_df["text_norm"] = jobs_df["text_description"].map(normalize_text)

    resumes_df["text_norm"] = resumes_df["text_description"].map(normalize_text)

    jobs_df["job_tokens"] = (jobs_df["title_norm"] + " " + jobs_df["text_norm"]).map(tokenize)
    jobs_df["title_tokens"] = jobs_df["title_norm"].map(tokenize)

    resumes_df["resume_tokens"] = resumes_df["text_norm"].map(tokenize)
    resumes_df["years_experience_estimate"] = resumes_df["text_norm"].map(
        estimate_years_experience
    )

    resume_tokens = resumes_df["resume_tokens"].tolist()
    resume_ids = resumes_df["id"].astype(str).tolist()
    resume_years = resumes_df["years_experience_estimate"].to_numpy(dtype=float)
    max_experience = float(np.max(resume_years)) if len(resume_years) else 0.0
    if max_experience <= 0.0:
        max_experience = 1.0

    bm25_index = build_bm25_index(resume_tokens)

    all_rows: list[dict[str, Any]] = []
    for job in jobs_df.itertuples(index=False):
        all_rows.extend(
            build_pairs_for_job(
                job_id=str(job.id),
                job_title=str(job.title_raw),
                job_tokens=list(job.job_tokens),
                job_title_tokens=list(job.title_tokens),
                bm25_index=bm25_index,
                resume_ids=resume_ids,
                resume_tokens=resume_tokens,
                resume_years=resume_years,
                max_experience=max_experience,
                top_k=args.top_k,
            )
        )

    pairs_df = pd.DataFrame(all_rows)
    if pairs_df.empty:
        pairs_df = pd.DataFrame(columns=OUTPUT_COLUMNS)
    else:
        pairs_df = pairs_df[OUTPUT_COLUMNS]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.review_out.parent.mkdir(parents=True, exist_ok=True)

    pairs_df.to_csv(args.out, index=False)

    review_df = sample_review_batch(pairs_df, seed=args.seed, top_k=args.top_k)
    review_df = review_df[OUTPUT_COLUMNS]
    review_df.to_csv(args.review_out, index=False)

    num_jobs = len(jobs_df)
    num_resumes = len(resumes_df)
    num_pairs = len(pairs_df)
    avg_candidates = (num_pairs / num_jobs) if num_jobs else 0.0

    print(f"number_of_jobs: {num_jobs}")
    print(f"number_of_resumes: {num_resumes}")
    print(f"number_of_generated_pairs: {num_pairs}")
    print(f"average_candidates_per_job: {avg_candidates:.2f}")


if __name__ == "__main__":
    main()
