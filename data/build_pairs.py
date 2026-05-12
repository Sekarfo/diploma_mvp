"""
Build candidate (job, resume) pairs with interpretable ranking features.

Inputs:
    resumes_consolidated.csv        (with person_id, past_titles, skills,
                                    total_years_experience, etc.)
    jobs_clean.csv                  (with job_id, job_title, job_skills_norm,
                                    job_years_required)
    resume_embeddings.npy           (N_resumes, 384), L2-normalized
    resume_ids.npy                  (N_resumes,) parallel person_ids
    job_embeddings.npy              (N_jobs, 384), L2-normalized
    job_ids.npy                     (N_jobs,) parallel job_ids

Output:
    pair_features.csv               ~115k rows of (job_id, resume_id, features...)
"""

from pathlib import Path
import ast
import re
import time

import numpy as np
import pandas as pd


# ----- config -----
RESUMES_CSV  = "resumes_consolidated.csv"
JOBS_CSV     = "jobs_clean.csv"
RESUME_EMB   = "resume_embeddings.npy"
JOB_EMB      = "job_embeddings.npy"
RESUME_IDS   = "resume_ids.npy"
JOB_IDS      = "job_ids.npy"
TOP_K        = 50                       # candidates per job
OUTPUT_CSV   = "pair_features.csv"


# ---------- helpers ----------

def parse_resume_skills(s: str) -> set[str]:
    """Resume skills are pipe-joined: 'python|sql|aws'."""
    if not isinstance(s, str) or not s:
        return set()
    return {x for x in s.split("|") if x}


def parse_job_skills(s: str) -> set[str]:
    """Job skills are stringified Python lists: "['python', 'sql']"."""
    if not isinstance(s, str) or not s:
        return set()
    try:
        return set(ast.literal_eval(s))
    except (ValueError, SyntaxError):
        return set()


def tokenize_title(s: str) -> set[str]:
    """Lowercase tokens from a title string, stripping noise words."""
    if not isinstance(s, str):
        return set()
    # split on non-alphanum, drop very short tokens and pure noise
    tokens = re.findall(r"[a-z0-9+#]+", s.lower())
    noise = {"sr", "jr", "the", "a", "an", "of", "and", "to", "in", "at", "i", "ii"}
    return {t for t in tokens if len(t) > 1 and t not in noise}


def title_overlap_ratio(job_title: str, resume_past_titles: str) -> float:
    """Fraction of job-title tokens that appear anywhere in resume's past titles."""
    job_tokens    = tokenize_title(job_title)
    resume_tokens = tokenize_title(resume_past_titles)
    if not job_tokens:
        return 0.0
    return len(job_tokens & resume_tokens) / len(job_tokens)


# ---------- main ----------

def main() -> None:
    print("Loading data...")
    resumes = pd.read_csv(RESUMES_CSV)
    jobs    = pd.read_csv(JOBS_CSV)
    resume_vectors = np.load(RESUME_EMB)
    job_vectors    = np.load(JOB_EMB)
    resume_ids     = np.load(RESUME_IDS, allow_pickle=True)
    job_ids        = np.load(JOB_IDS, allow_pickle=True)

    print(f"  resumes: {len(resumes):,}  vectors: {resume_vectors.shape}")
    print(f"  jobs:    {len(jobs):,}     vectors: {job_vectors.shape}")

    # Sanity check: embeddings line up with CSVs
    assert len(resume_vectors) == len(resumes), "resume embedding count mismatch"
    assert len(job_vectors) == len(jobs),       "job embedding count mismatch"

    # Index resumes and jobs by their IDs for fast lookup
    resumes = resumes.set_index("person_id")
    jobs    = jobs.set_index("job_id")

    # Pre-parse expensive columns ONCE rather than per-pair
    print("Pre-parsing skill sets and title tokens...")
    resumes["_skill_set"]    = resumes["skills"].apply(parse_resume_skills)
    resumes["_title_tokens"] = resumes["past_titles"].apply(tokenize_title)
    jobs["_skill_set"]       = jobs["job_skills_norm"].apply(parse_job_skills)
    jobs["_title_tokens"]    = jobs["job_title"].apply(tokenize_title)

    # ---- retrieval: for each job, find top-K resumes by cosine ----
    # Both embedding matrices are L2-normalized, so dot product = cosine similarity.
    print(f"\nRetrieving top-{TOP_K} resumes per job...")
    t0 = time.time()
    # similarity matrix: (N_jobs, N_resumes). For 2296 x 18174 this is ~167 MB float32.
    sim = job_vectors @ resume_vectors.T
    # For each row (job), get indices of top-K resumes by similarity.
    # argpartition is faster than full argsort when we only need top-K.
    top_idx = np.argpartition(-sim, kth=TOP_K, axis=1)[:, :TOP_K]
    # Re-sort those top-K by actual score (argpartition doesn't guarantee order)
    for i in range(len(top_idx)):
        row = top_idx[i]
        top_idx[i] = row[np.argsort(-sim[i, row])]
    print(f"  done in {time.time() - t0:.1f}s")

    # ---- feature computation per pair ----
    print("\nComputing features for each pair...")
    rows = []
    t0 = time.time()
    for job_pos in range(len(jobs)):
        job_id   = job_ids[job_pos]
        job_row  = jobs.loc[job_id]
        job_skills        = job_row["_skill_set"]
        job_title_tokens  = job_row["_title_tokens"]
        job_years         = float(job_row.get("job_years_required") or 0.0)

        for rank, res_pos in enumerate(top_idx[job_pos], start=1):
            res_pos = int(res_pos)
            resume_id  = resume_ids[res_pos]
            resume_row = resumes.loc[resume_id]
            resume_skills       = resume_row["_skill_set"]
            resume_title_tokens = resume_row["_title_tokens"]
            resume_years        = float(resume_row.get("total_years_experience") or 0.0)

            # skill features
            overlap = job_skills & resume_skills
            skill_overlap_count = len(overlap)
            skill_overlap_ratio = (
                skill_overlap_count / len(job_skills) if job_skills else 0.0
            )

            # title features
            if job_title_tokens:
                title_overlap = (
                    len(job_title_tokens & resume_title_tokens) / len(job_title_tokens)
                )
            else:
                title_overlap = 0.0

            # experience features
            years_gap = resume_years - job_years
            experience_match_flag = 1 if years_gap >= 0 else 0

            rows.append({
                "job_id":                job_id,
                "resume_id":             resume_id,
                "retrieval_rank":        rank,
                "embedding_cosine":      float(sim[job_pos, res_pos]),
                "skill_overlap_count":   skill_overlap_count,
                "skill_overlap_ratio":   round(skill_overlap_ratio, 4),
                "title_overlap_ratio":   round(title_overlap, 4),
                "years_gap":             round(years_gap, 2),
                "experience_match_flag": experience_match_flag,
                "resume_years_experience": round(resume_years, 2),
                "job_years_required":    round(job_years, 2),
            })

        if (job_pos + 1) % 200 == 0:
            elapsed = time.time() - t0
            print(f"  {job_pos + 1}/{len(jobs)} jobs processed ({elapsed:.1f}s)")

    pairs = pd.DataFrame(rows)
    print(f"\nTotal pairs: {len(pairs):,}")
    print(f"Time: {time.time() - t0:.1f}s")

    # ---- save ----
    pairs.to_csv(OUTPUT_CSV, index=False)
    print(f"Saved -> {OUTPUT_CSV}")

    # ---- quick sanity summary ----
    print("\n--- feature distributions ---")
    print(pairs[[
        "embedding_cosine", "skill_overlap_count", "skill_overlap_ratio",
        "title_overlap_ratio", "years_gap", "experience_match_flag"
    ]].describe().round(3))

    print("\n--- pairs per job ---")
    counts = pairs.groupby("job_id").size()
    print(f"  min={counts.min()}  max={counts.max()}  median={counts.median()}")

    print("\n--- example: top-5 pairs for one job ---")
    sample_job = pairs["job_id"].iloc[0]
    print(f"job_id = {sample_job}")
    print(pairs[pairs["job_id"] == sample_job].head(5).to_string(index=False))


if __name__ == "__main__":
    main()