from __future__ import annotations

import math
import re
from collections import Counter
from typing import Iterable

import pandas as pd

from backend.app.config import SKILL_KEYWORDS

TOKEN_PATTERN = re.compile(r"c\+\+|c#|\.net|[a-z0-9]+(?:[+#.][a-z0-9]+)*")
YEARS_SINGLE_PATTERN = re.compile(r"\b(\d{1,2})\+?\s*(?:years?|yrs?)\b")
DATE_RANGE_PATTERN = re.compile(r"\b((?:19|20)\d{2})\s*-\s*((?:19|20)\d{2})\b")
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
    "experience",
    "years",
    "year",
    "role",
    "job",
}


def _normalize_text(text: str | None) -> str:
    return str(text or "").lower().strip()


def _tokenize(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(_normalize_text(text))


def _extract_years_experience(text: str) -> float:
    normalized = _normalize_text(text)
    estimates: list[float] = []

    for years in YEARS_SINGLE_PATTERN.findall(normalized):
        value = int(years)
        if 0 <= value <= 50:
            estimates.append(float(value))

    for start, end in DATE_RANGE_PATTERN.findall(normalized):
        low = int(start)
        high = int(end)
        if 1900 <= low <= 2100 and 1900 <= high <= 2100 and high >= low:
            estimates.append(float(high - low))

    return max(estimates) if estimates else 0.0


def _extract_skill_tokens(tokens: Iterable[str]) -> set[str]:
    token_set = set(tokens)
    keyword_tokens = set()
    for keyword in SKILL_KEYWORDS:
        pieces = _tokenize(keyword)
        if not pieces:
            continue
        if len(pieces) == 1 and pieces[0] in token_set:
            keyword_tokens.add(pieces[0])
        elif all(piece in token_set for piece in pieces):
            keyword_tokens.update(pieces)

    heuristic_tokens = {
        t for t in token_set
        if t not in STOPWORDS and len(t) > 2 and any(ch.isalpha() for ch in t)
    }
    return keyword_tokens | heuristic_tokens


def _extract_keyword_skills(text: str) -> set[str]:
    normalized = _normalize_text(text)
    matched: set[str] = set()
    for skill in SKILL_KEYWORDS:
        skill_l = skill.lower()
        if skill_l in normalized:
            matched.add(skill_l)
    return matched


def _bm25_scores(query_tokens: list[str], document_tokens: list[list[str]]) -> list[float]:
    if not query_tokens or not document_tokens:
        return [0.0 for _ in document_tokens]

    n_docs = len(document_tokens)
    avg_doc_len = sum(len(doc) for doc in document_tokens) / max(1, n_docs)
    k1 = 1.5
    b = 0.75

    df = Counter()
    for doc in document_tokens:
        df.update(set(doc))

    query_counts = Counter(query_tokens)
    scores: list[float] = []

    for doc in document_tokens:
        doc_tf = Counter(doc)
        doc_len = len(doc)
        score = 0.0
        for token, qf in query_counts.items():
            n = df.get(token, 0)
            idf = math.log(1.0 + (n_docs - n + 0.5) / (n + 0.5))
            tf = doc_tf.get(token, 0)
            if tf == 0:
                continue
            numerator = tf * (k1 + 1.0)
            denominator = tf + k1 * (1.0 - b + b * (doc_len / max(avg_doc_len, 1e-9)))
            score += qf * idf * (numerator / denominator)
        scores.append(float(score))
    return scores


class FeatureBuilderService:
    """Builds ranker-compatible features from a job text and local candidate set."""

    def build_candidate_features(
        self,
        job_title: str,
        job_description: str,
        candidates_df: pd.DataFrame,
    ) -> pd.DataFrame:
        if candidates_df.empty:
            raise ValueError("No candidates available to build features.")

        if "resume_text" not in candidates_df.columns:
            raise ValueError("candidates_df must include resume_text column.")

        job_text = f"{job_title} {job_description}".strip()
        job_tokens = _tokenize(job_text)
        title_tokens = [t for t in _tokenize(job_title) if t not in STOPWORDS]
        job_skill_tokens = _extract_skill_tokens(job_tokens)
        job_keyword_skills = _extract_keyword_skills(job_text)

        candidate_tokens = [
            _tokenize(f"{row.get('skills_text', '')} {row.get('resume_text', '')}")
            for row in candidates_df.to_dict(orient="records")
        ]
        bm25 = _bm25_scores(job_tokens, candidate_tokens)

        bm25_min = min(bm25) if bm25 else 0.0
        bm25_max = max(bm25) if bm25 else 0.0
        if bm25_max > bm25_min:
            normalized_bm25 = [(s - bm25_min) / (bm25_max - bm25_min) for s in bm25]
        else:
            normalized_bm25 = [0.0 for _ in bm25]

        rows = []
        for idx, candidate in enumerate(candidates_df.to_dict(orient="records")):
            tokens = candidate_tokens[idx]
            token_set = set(tokens)
            candidate_skill_tokens = _extract_skill_tokens(tokens)
            overlap_tokens = job_skill_tokens & candidate_skill_tokens
            candidate_keyword_skills = _extract_keyword_skills(
                f"{candidate.get('skills_text', '')} {candidate.get('resume_text', '')}"
            )
            matched_skills = sorted(job_keyword_skills & candidate_keyword_skills)

            overlap_count = len(overlap_tokens)
            overlap_ratio = overlap_count / len(job_skill_tokens) if job_skill_tokens else 0.0
            title_overlap_ratio = (
                len(set(title_tokens) & token_set) / len(set(title_tokens))
                if title_tokens else 0.0
            )
            years = _extract_years_experience(candidate.get("resume_text", ""))

            rows.append(
                {
                    **candidate,
                    "bm25_score": float(bm25[idx]),
                    "normalized_bm25_score": float(normalized_bm25[idx]),
                    "exact_skill_overlap_count": float(overlap_count),
                    "exact_skill_overlap_ratio": float(overlap_ratio),
                    "title_token_overlap_ratio": float(title_overlap_ratio),
                    "years_experience_estimate": float(years),
                    "matched_skills": matched_skills,
                }
            )

        return pd.DataFrame(rows)
