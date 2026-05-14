from __future__ import annotations

import ast
import re
from typing import Any

import numpy as np
import pandas as pd

_LIST_SPLIT_PATTERN = re.compile(r"[|,;]")
_WORD_PATTERN = re.compile(r"[a-z][a-z0-9+\-./#]{0,29}")
_PUNCT_STRIP = re.compile(r"[^a-z0-9+\-./# ]+")

_SKILL_STOP_WORDS = frozenset({
    "a", "an", "and", "or", "the", "of", "in", "to", "for", "with", "on",
    "at", "by", "from", "as", "is", "it", "this", "that", "be", "are",
    "was", "were", "we", "they", "you", "etc", "via", "using", "use",
    "used", "able", "also", "any", "such", "into", "over", "than", "then",
    "these", "those", "their", "them", "our", "ours", "very",
})


def _split_pipe_list(value: Any) -> list[str]:
    """Splits a pipe/comma/semicolon-separated string into a deduplicated lowercase list."""
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        items = [str(item).strip() for item in value]
    elif isinstance(value, np.ndarray):
        items = [str(item).strip() for item in value.tolist()]
    elif isinstance(value, str):
        text = value.strip()
        if not text or text.lower() == "nan":
            return []
        if text.startswith("[") and text.endswith("]"):
            try:
                parsed = ast.literal_eval(text)
                if isinstance(parsed, (list, tuple, set)):
                    items = [str(item).strip() for item in parsed]
                else:
                    items = [str(parsed).strip()]
            except Exception:
                items = [piece.strip(" '\"") for piece in _LIST_SPLIT_PATTERN.split(text[1:-1])]
        else:
            items = [piece.strip() for piece in _LIST_SPLIT_PATTERN.split(text)]
    else:
        try:
            if pd.isna(value):
                return []
        except Exception:
            pass
        items = [str(value).strip()]

    cleaned: list[str] = []
    seen: set[str] = set()
    for item in items:
        token = item.strip().lower().strip(" '\"")
        if not token or token == "nan":
            continue
        if token not in seen:
            cleaned.append(token)
            seen.add(token)
    return cleaned


def _tokenize_skill_bag(phrases: list[str]) -> list[str]:
    """Turns raw resume "skill" phrases into an atomic skill bag.

    The cleaned resume dataset stores `skills` as a `|`-separated mix of single tokens
    (`sql`), short concepts (`machine learning`), URLs and full achievement sentences
    (`backend development with custom post types ...`). For set-intersection-based
    `skill_overlap` against atomic job skills we need to compress this into a bag of
    short tokens.

    Strategy:
      - drop URLs and empty strings
      - split slash- and hyphen-joined compounds into atomic parts AND keep the
        original combined form (so "git/github" yields "git", "github" AND
        "git/github" — matching atomic job skills like "git" while preserving
        compound-as-phrase matches)
      - keep phrases of 1–3 words as-is (preserves multi-word skills like "machine learning")
      - for longer phrases, emit individual non-stopword tokens and bigrams
    """
    tokens: set[str] = set()
    for phrase in phrases:
        text = str(phrase).strip().lower()
        if not text or text.startswith(("http://", "https://", "www.")):
            continue
        text = _PUNCT_STRIP.sub(" ", text)

        # First pass: keep slash/hyphen-joined tokens intact (so "node.js", "c++",
        # "git/github" survive as single tokens for compound-form matching).
        words_compound = [w for w in text.split() if w]
        # Second pass: also explode slash- and hyphen-joined compounds so atomic
        # job skills like "git" match when resumes write them as "git/github" or
        # "object-oriented". This is the bug fix — without splitting these,
        # "git" never matched "git/github" tokens in resume_skills_norm.
        text_split = text.replace("/", " ").replace("-", " ")
        words_split = [w for w in text_split.split() if w]

        # Use the more atomic split for phrase / individual / bigram extraction,
        # but also retain the compound form as a phrase token when short.
        words = words_split if words_split else words_compound
        if not words:
            continue
        if 1 <= len(words) <= 3:
            tokens.add(" ".join(words))
        if 1 <= len(words_compound) <= 3 and words_compound != words:
            # Preserve compound form (e.g. "git/github", "object-oriented")
            tokens.add(" ".join(words_compound))

        # Always emit individual tokens — fixes the slash/hyphen bug
        for word in words:
            if 2 <= len(word) <= 30 and word not in _SKILL_STOP_WORDS and not word.startswith("http"):
                tokens.add(word)
        # Also emit compound tokens individually (e.g. "node.js", "c++")
        for word in words_compound:
            if 2 <= len(word) <= 30 and word not in _SKILL_STOP_WORDS and not word.startswith("http"):
                tokens.add(word)

        for i in range(len(words) - 1):
            w1, w2 = words[i], words[i + 1]
            if (
                len(w1) >= 2
                and len(w2) >= 2
                and w1 not in _SKILL_STOP_WORDS
                and w2 not in _SKILL_STOP_WORDS
            ):
                tokens.add(f"{w1} {w2}")
    return sorted(tokens)


def normalize_jobs_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Maps raw jobs_clean.csv to the runtime schema expected by backend."""
    out = df.copy()
    if "job_id" not in out.columns:
        raise ValueError("jobs dataset missing required column: job_id")

    if "job_title" not in out.columns:
        out["job_title"] = ""
    if "job_description" not in out.columns:
        out["job_description"] = ""
    if "job_text" not in out.columns:
        out["job_text"] = (out["job_title"].fillna("") + " " + out["job_description"].fillna("")).str.strip()
    if "job_skills_norm" not in out.columns:
        out["job_skills_norm"] = [[] for _ in range(len(out))]
    if "job_years_required" not in out.columns:
        out["job_years_required"] = 0.0

    out["job_id"] = out["job_id"].astype(str)
    out["job_title"] = out["job_title"].fillna("").astype(str)
    out["job_description"] = out["job_description"].fillna("").astype(str)
    out["job_text"] = out["job_text"].fillna("").astype(str)
    out["job_skills_norm"] = out["job_skills_norm"].apply(_split_pipe_list)
    out["job_years_required"] = pd.to_numeric(out["job_years_required"], errors="coerce").fillna(0.0).astype("float32")

    keep = [
        "job_id",
        "job_title",
        "job_description",
        "job_text",
        "job_skills_norm",
        "job_years_required",
    ]
    return out[keep].drop_duplicates(subset=["job_id"]).reset_index(drop=True)


def normalize_resumes_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Maps raw resumes_clean.csv columns into runtime schema.

    Raw columns: person_id, abilities_text, highest_education, total_years_experience,
                 num_past_roles, past_titles, past_firms, skills, num_skills, resume_text.
    """
    out = df.copy()
    rename_map: dict[str, str] = {}
    if "person_id" in out.columns and "resume_id" not in out.columns:
        rename_map["person_id"] = "resume_id"
    if "total_years_experience" in out.columns and "resume_years_experience" not in out.columns:
        rename_map["total_years_experience"] = "resume_years_experience"
    out = out.rename(columns=rename_map)

    if "resume_id" not in out.columns:
        raise ValueError("resumes dataset missing resume_id / person_id column")
    if "resume_text" not in out.columns:
        raise ValueError("resumes dataset missing resume_text column")

    out["resume_id"] = out["resume_id"].astype(str)
    out["resume_text"] = out["resume_text"].fillna("").astype(str)

    skill_source = out["skills"] if "skills" in out.columns else pd.Series([""] * len(out))
    out["resume_skills_norm"] = skill_source.apply(lambda x: _tokenize_skill_bag(_split_pipe_list(x)))

    if "past_titles" in out.columns:
        out["resume_titles_norm"] = out["past_titles"].apply(_split_pipe_list)
    else:
        out["resume_titles_norm"] = [[] for _ in range(len(out))]

    out["resume_years_experience"] = (
        pd.to_numeric(out.get("resume_years_experience", 0.0), errors="coerce").fillna(0.0).astype("float32")
    )

    keep = [
        "resume_id",
        "resume_text",
        "resume_skills_norm",
        "resume_titles_norm",
        "resume_years_experience",
    ]
    return out[keep].drop_duplicates(subset=["resume_id"]).reset_index(drop=True)
