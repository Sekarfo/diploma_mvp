from __future__ import annotations

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
RAW_DIR = DATA_DIR / "Clear"
EMBEDDINGS_DIR = DATA_DIR / "embeddings"

RAW_JOBS_CSV = RAW_DIR / "jobs_clean.csv"
RAW_RESUMES_CSV = RAW_DIR / "resumes_clean.csv"

JOB_EMBEDDINGS_NPY = EMBEDDINGS_DIR / "job_embeddings.npy"
RESUME_EMBEDDINGS_NPY = EMBEDDINGS_DIR / "resume_embeddings.npy"

DEFAULT_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "BAAI/bge-large-en-v1.5")
DEFAULT_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "32"))
DEFAULT_MAX_SEQ_LENGTH = int(os.getenv("EMBEDDING_MAX_SEQ_LENGTH", "512"))

ELASTICSEARCH_URL = os.getenv("ELASTICSEARCH_URL", "http://127.0.0.1:9200")
ELASTICSEARCH_USERNAME = os.getenv("ELASTICSEARCH_USERNAME")
ELASTICSEARCH_PASSWORD = os.getenv("ELASTICSEARCH_PASSWORD")
ELASTICSEARCH_INDEX = os.getenv("ELASTICSEARCH_INDEX", "resumes_index")

BGE_QUERY_INSTRUCTION = "Represent this query for retrieving relevant passages: "
