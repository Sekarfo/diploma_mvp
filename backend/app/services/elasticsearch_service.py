from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from elasticsearch import Elasticsearch

from backend.app.config import Settings, get_settings
from backend.app.services.errors import ElasticsearchUnavailableError
from backend.app.services.runtime_utils import parse_list_col, to_float

logger = logging.getLogger(__name__)


class ElasticsearchRetrievalService:
    """Retrieves top-K candidate resumes via hybrid kNN + BM25 search on Elasticsearch."""

    KNN_BOOST = 1.0
    BM25_BOOST = 0.5

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def _connect(self) -> Elasticsearch:
        kwargs: dict[str, Any] = {
            "hosts": [self.settings.elasticsearch_url],
            "request_timeout": 60,
            "verify_certs": False,
        }
        if self.settings.elasticsearch_username and self.settings.elasticsearch_password:
            kwargs["basic_auth"] = (
                self.settings.elasticsearch_username,
                self.settings.elasticsearch_password,
            )

        try:
            client = Elasticsearch(**kwargs)
            if not client.ping():
                raise ElasticsearchUnavailableError(
                    f"Could not connect to Elasticsearch at {self.settings.elasticsearch_url}"
                )
            return client
        except ElasticsearchUnavailableError:
            raise
        except Exception as exc:
            raise ElasticsearchUnavailableError(
                f"Elasticsearch connection failed: {exc}"
            ) from exc

    def retrieve_hits(
        self,
        *,
        query_vector: np.ndarray,
        top_k: int,
        num_candidates: int,
        index_name: str | None = None,
        query_text: str | None = None,
        query_skills: list[str] | None = None,
        query_title: str | None = None,
    ) -> list[dict[str, Any]]:
        """Hybrid retrieval: kNN over dense embedding + lexical BM25 over text/skills/titles.

        When `query_text` / `query_skills` / `query_title` are omitted the call degrades to
        a pure kNN search, matching the previous behavior.
        """
        index = index_name or self.settings.elasticsearch_index_name
        knn_block = {
            "field": "embedding",
            "query_vector": query_vector.tolist(),
            "k": top_k,
            "num_candidates": max(num_candidates, top_k),
            "boost": self.KNN_BOOST,
        }

        should_clauses: list[dict[str, Any]] = []
        text_blob = (query_text or "").strip()
        if text_blob:
            should_clauses.append(
                {
                    "match": {
                        "resume_text": {
                            "query": text_blob,
                            "boost": self.BM25_BOOST,
                        }
                    }
                }
            )
        cleaned_skills = [s.strip().lower() for s in (query_skills or []) if str(s).strip()]
        if cleaned_skills:
            should_clauses.append(
                {
                    "terms": {
                        "resume_skills_norm": cleaned_skills,
                        "boost": self.BM25_BOOST,
                    }
                }
            )
        title_blob = (query_title or "").strip()
        if title_blob:
            should_clauses.append(
                {
                    "match": {
                        "resume_titles_norm": {
                            "query": title_blob,
                            "boost": self.BM25_BOOST * 0.5,
                        }
                    }
                }
            )

        search_kwargs: dict[str, Any] = {
            "index": index,
            "knn": knn_block,
            "_source": [
                "resume_id",
                "resume_text",
                "resume_skills_norm",
                "resume_titles_norm",
                "resume_years_experience",
            ],
            "size": top_k,
        }
        if should_clauses:
            search_kwargs["query"] = {"bool": {"should": should_clauses, "minimum_should_match": 0}}

        try:
            client = self._connect()
            response = client.search(**search_kwargs)
            hits = response.get("hits", {}).get("hits", [])
            for hit in hits:
                hit["retrieval_score_raw"] = to_float(hit.get("_score", 0.0), default=0.0)
            logger.info(
                "Elasticsearch retrieval completed: hits=%s mode=%s",
                len(hits),
                "hybrid" if should_clauses else "knn",
            )
            return hits
        except ElasticsearchUnavailableError:
            raise
        except Exception as exc:
            raise ElasticsearchUnavailableError(f"Elasticsearch query failed: {exc}") from exc

    @staticmethod
    def retrieve_hits_from_csv(retrieved_csv: Path, top_k: int) -> list[dict[str, Any]]:
        df = pd.read_csv(retrieved_csv).copy()
        if "resume_id" not in df.columns:
            raise ValueError(f"retrieved csv is missing required column resume_id: {retrieved_csv}")
        if "retrieval_rank" not in df.columns:
            df["retrieval_rank"] = np.arange(1, len(df) + 1)

        df["retrieval_rank"] = pd.to_numeric(df["retrieval_rank"], errors="coerce").fillna(999999)
        df = df.sort_values("retrieval_rank", ascending=True).head(top_k).reset_index(drop=True)

        hits: list[dict[str, Any]] = []
        for _, row in df.iterrows():
            hits.append(
                {
                    "_score": to_float(row.get("elastic_score", 0.0), default=0.0),
                    "retrieval_score_raw": to_float(row.get("elastic_score", 0.0), default=0.0),
                    "_source": {
                        "resume_id": str(row.get("resume_id", "")),
                        "resume_text": str(row.get("resume_text", "")),
                        "resume_skills_norm": parse_list_col(row.get("resume_skills_norm", [])),
                        "resume_titles_norm": parse_list_col(row.get("resume_titles_norm", [])),
                        "resume_years_experience": to_float(row.get("resume_years_experience", 0.0), default=0.0),
                    },
                }
            )
        return hits
