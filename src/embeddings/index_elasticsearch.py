from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from elasticsearch import Elasticsearch, helpers

from .config import (
    ELASTICSEARCH_INDEX,
    ELASTICSEARCH_PASSWORD,
    ELASTICSEARCH_URL,
    ELASTICSEARCH_USERNAME,
    RAW_RESUMES_CSV,
    RESUME_EMBEDDINGS_NPY,
)
from .schemas import normalize_resumes_dataframe

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Index resumes + embeddings into Elasticsearch.")
    parser.add_argument("--index-name", default=ELASTICSEARCH_INDEX)
    parser.add_argument("--recreate-index", action="store_true")
    parser.add_argument("--chunk-size", type=int, default=400)
    parser.add_argument("--resumes-csv", type=Path, default=RAW_RESUMES_CSV)
    parser.add_argument("--embeddings", type=Path, default=RESUME_EMBEDDINGS_NPY)
    return parser.parse_args()


def _connect() -> Elasticsearch:
    kwargs: dict[str, Any] = {
        "hosts": [ELASTICSEARCH_URL],
        "request_timeout": 60,
        "verify_certs": False,
    }
    if ELASTICSEARCH_USERNAME and ELASTICSEARCH_PASSWORD:
        kwargs["basic_auth"] = (ELASTICSEARCH_USERNAME, ELASTICSEARCH_PASSWORD)
    client = Elasticsearch(**kwargs)
    if not client.ping():
        raise ConnectionError(f"Cannot connect to Elasticsearch at {ELASTICSEARCH_URL}")
    return client


def _index_mapping(dims: int) -> dict[str, Any]:
    return {
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "analysis": {
                "analyzer": {
                    "resume_text_analyzer": {
                        "type": "standard",
                        "stopwords": "_english_",
                    }
                }
            },
        },
        "mappings": {
            "properties": {
                "resume_id": {"type": "keyword"},
                "resume_text": {
                    "type": "text",
                    "analyzer": "resume_text_analyzer",
                    "similarity": "BM25",
                },
                "resume_skills_norm": {"type": "keyword"},
                "resume_titles_norm": {"type": "keyword"},
                "resume_years_experience": {"type": "float"},
                "embedding": {
                    "type": "dense_vector",
                    "dims": dims,
                    "index": True,
                    "similarity": "cosine",
                },
            }
        },
    }


def _create_index(client: Elasticsearch, name: str, dims: int, recreate: bool) -> None:
    exists = client.indices.exists(index=name)
    if recreate and exists:
        logger.info("Deleting existing index %s", name)
        client.indices.delete(index=name)
        exists = False
    if exists:
        logger.info("Index %s already exists. Use --recreate-index to rebuild.", name)
        return
    body = _index_mapping(dims)
    client.indices.create(index=name, settings=body["settings"], mappings=body["mappings"])
    logger.info("Created index %s with dims=%s", name, dims)


def _bulk_actions(df: pd.DataFrame, embeddings: np.ndarray, index_name: str):
    for position, row in df.reset_index(drop=True).iterrows():
        yield {
            "_op_type": "index",
            "_index": index_name,
            "_id": str(row["resume_id"]),
            "_source": {
                "resume_id": str(row["resume_id"]),
                "resume_text": str(row.get("resume_text", "")),
                "resume_skills_norm": list(row.get("resume_skills_norm", []) or []),
                "resume_titles_norm": list(row.get("resume_titles_norm", []) or []),
                "resume_years_experience": float(row.get("resume_years_experience", 0.0) or 0.0),
                "embedding": embeddings[position].astype(float).tolist(),
            },
        }


def main() -> None:
    args = parse_args()
    logger.info("Loading raw resumes from %s", args.resumes_csv)
    resumes_df = normalize_resumes_dataframe(pd.read_csv(args.resumes_csv))
    logger.info("Loading embeddings from %s", args.embeddings)
    embeddings = np.load(args.embeddings)

    if len(resumes_df) != len(embeddings):
        raise ValueError(
            f"Row count mismatch: resumes={len(resumes_df)} embeddings={len(embeddings)}"
        )
    if embeddings.ndim != 2 or embeddings.shape[1] <= 0:
        raise ValueError(f"Unexpected embedding shape: {embeddings.shape}")

    client = _connect()
    _create_index(client, args.index_name, int(embeddings.shape[1]), recreate=args.recreate_index)

    success, errors = helpers.bulk(
        client,
        _bulk_actions(resumes_df, embeddings, args.index_name),
        chunk_size=args.chunk_size,
        request_timeout=180,
        raise_on_error=False,
        stats_only=False,
    )
    client.indices.refresh(index=args.index_name)
    indexed_count = client.count(index=args.index_name)["count"]

    logger.info(
        "Indexed index=%s resumes=%s dims=%s bulk_success=%s docs_in_index=%s errors=%s",
        args.index_name,
        len(resumes_df),
        int(embeddings.shape[1]),
        success,
        indexed_count,
        len(errors) if errors else 0,
    )
    if errors:
        logger.warning("First bulk error: %s", errors[0])


if __name__ == "__main__":
    main()
