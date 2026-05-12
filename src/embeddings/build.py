from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from .config import (
    BGE_QUERY_INSTRUCTION,
    DEFAULT_BATCH_SIZE,
    DEFAULT_MAX_SEQ_LENGTH,
    DEFAULT_MODEL_NAME,
    EMBEDDINGS_DIR,
    JOB_EMBEDDINGS_NPY,
    RAW_JOBS_CSV,
    RAW_RESUMES_CSV,
    RESUME_EMBEDDINGS_NPY,
)
from .schemas import normalize_jobs_dataframe, normalize_resumes_dataframe

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Encode jobs and resumes with the configured semantic model.")
    parser.add_argument("--model-name", default=DEFAULT_MODEL_NAME)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--max-seq-length", type=int, default=DEFAULT_MAX_SEQ_LENGTH)
    parser.add_argument("--device", default=None, help="cuda / cuda:0 / cpu. Auto-detect if omitted.")
    parser.add_argument("--jobs-csv", type=Path, default=RAW_JOBS_CSV)
    parser.add_argument("--resumes-csv", type=Path, default=RAW_RESUMES_CSV)
    parser.add_argument("--disable-query-instruction", action="store_true")
    return parser.parse_args()


def _select_device(preferred: str | None) -> str:
    if preferred:
        return preferred
    try:
        import torch  # type: ignore

        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"


def _encode(model, texts: list[str], batch_size: int) -> np.ndarray:
    vectors = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=True,
        normalize_embeddings=True,
        convert_to_numpy=True,
    )
    return np.asarray(vectors, dtype="float32")


def main() -> None:
    args = parse_args()
    EMBEDDINGS_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("Loading raw jobs from %s", args.jobs_csv)
    jobs_df = normalize_jobs_dataframe(pd.read_csv(args.jobs_csv))
    logger.info("Loading raw resumes from %s", args.resumes_csv)
    resumes_df = normalize_resumes_dataframe(pd.read_csv(args.resumes_csv))
    logger.info("Counts: jobs=%s resumes=%s", len(jobs_df), len(resumes_df))

    from sentence_transformers import SentenceTransformer

    device = _select_device(args.device)
    logger.info("Loading SentenceTransformer model=%s device=%s", args.model_name, device)
    model = SentenceTransformer(args.model_name, device=device)
    model.max_seq_length = args.max_seq_length

    job_texts = jobs_df["job_text"].astype(str).tolist()
    if not args.disable_query_instruction:
        job_texts = [f"{BGE_QUERY_INSTRUCTION}{text}" for text in job_texts]

    logger.info("Encoding %s job documents (max_seq_length=%s)", len(job_texts), args.max_seq_length)
    job_embeddings = _encode(model, job_texts, args.batch_size)

    resume_texts = resumes_df["resume_text"].astype(str).tolist()
    logger.info("Encoding %s resume documents (max_seq_length=%s)", len(resume_texts), args.max_seq_length)
    resume_embeddings = _encode(model, resume_texts, args.batch_size)

    if job_embeddings.shape[1] != resume_embeddings.shape[1]:
        raise RuntimeError(
            f"Embedding dim mismatch: jobs={job_embeddings.shape[1]} resumes={resume_embeddings.shape[1]}"
        )

    np.save(JOB_EMBEDDINGS_NPY, job_embeddings)
    np.save(RESUME_EMBEDDINGS_NPY, resume_embeddings)
    logger.info("Saved %s shape=%s", JOB_EMBEDDINGS_NPY, job_embeddings.shape)
    logger.info("Saved %s shape=%s", RESUME_EMBEDDINGS_NPY, resume_embeddings.shape)


if __name__ == "__main__":
    main()
