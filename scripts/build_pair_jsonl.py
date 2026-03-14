#!/usr/bin/env python3
"""
Build parsed JSONL datasets for vacancies and resumes from raw CSV files.

Usage:
    uv run --no-project python scripts/build_parsed_jsonl.py
"""

from __future__ import annotations

import argparse
import ast
import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


VACANCY_FILENAME = "job_title_des.csv"
RESUME_FILENAME = "resume_data.csv"


def normalize_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower()).strip()


def read_rows(csv_path: Path) -> tuple[list[dict[str, str]], dict[str, str]]:
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            with csv_path.open("r", encoding=encoding, newline="") as handle:
                reader = csv.DictReader(handle)
                rows = [dict(row) for row in reader]
                fieldnames = reader.fieldnames or []
                key_map = {
                    normalize_key(field): field
                    for field in fieldnames
                    if field is not None
                }
                return rows, key_map
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f"Unable to decode CSV: {csv_path}")


def get_value(row: dict[str, str], key_map: dict[str, str], *aliases: str) -> str:
    for alias in aliases:
        actual_key = key_map.get(normalize_key(alias))
        if actual_key is None:
            continue
        value = row.get(actual_key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def flatten_items(value: object) -> Iterable[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        out: list[str] = []
        for item in value:
            out.extend(flatten_items(item))
        return out
    return [str(value)]


def parse_maybe_list(raw_text: str) -> str:
    text = (raw_text or "").strip()
    if not text:
        return ""
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = ast.literal_eval(text)
        except (SyntaxError, ValueError):
            return text
        values = [
            piece.strip()
            for piece in flatten_items(parsed)
            if piece and piece.strip() and piece.strip().lower() not in {"none", "n/a", "na"}
        ]
        return ", ".join(values)
    return text


HEADER_FOOTER_PATTERNS = (
    re.compile(r"^\s*(resume|curriculum vitae|cv)\s*$", re.IGNORECASE),
    re.compile(r"^\s*page\s+\d+(\s*(/|of)\s*\d+)?\s*$", re.IGNORECASE),
)


def is_obvious_header_or_footer(line: str) -> bool:
    compact = line.strip()
    if not compact:
        return False
    return any(pattern.match(compact) for pattern in HEADER_FOOTER_PATTERNS)


def clean_text(raw_text: str) -> str:
    lines = raw_text.splitlines()
    kept = [line for line in lines if not is_obvious_header_or_footer(line)]
    text = "\n".join(kept) if kept else raw_text
    text = text.lower()
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"\s+\n", "\n", text)
    text = re.sub(r"\n\s+", "\n", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


@dataclass(frozen=True)
class ResumeField:
    label: str
    aliases: tuple[str, ...]


RESUME_FIELDS: tuple[ResumeField, ...] = (
    ResumeField("career objective", ("career_objective", "career objective")),
    ResumeField("skills", ("skills",)),
    ResumeField(
        "education institutions",
        ("educational_institution_name", "educational institution name"),
    ),
    ResumeField("degrees", ("degree_names", "degree names")),
    ResumeField("passing years", ("passing_years", "passing years")),
    ResumeField(
        "educational results",
        ("educational_results", "educational results"),
    ),
    ResumeField("result types", ("result_types", "result types")),
    ResumeField(
        "major fields",
        ("major_field_of_studies", "major field of studies"),
    ),
    ResumeField(
        "companies",
        ("professional_company_names", "professional company names"),
    ),
    ResumeField("company urls", ("company_urls", "company urls")),
    ResumeField("start dates", ("start_dates", "start dates")),
    ResumeField("end dates", ("end_dates", "end dates")),
    ResumeField(
        "related skills in job",
        ("related_skils_in_job", "related skills in job"),
    ),
    ResumeField("positions", ("positions",)),
    ResumeField("locations", ("locations",)),
    ResumeField("responsibilities", ("responsibilities",)),
    ResumeField(
        "extra curricular activity types",
        ("extra_curricular_activity_types", "extra curricular activity types"),
    ),
    ResumeField(
        "extra curricular organizations",
        (
            "extra_curricular_organization_names",
            "extra curricular organization names",
        ),
    ),
    ResumeField(
        "extra curricular links",
        (
            "extra_curricular_organization_links",
            "extra curricular organization links",
        ),
    ),
    ResumeField("roles", ("role_positions", "role positions")),
    ResumeField("languages", ("languages",)),
    ResumeField("proficiency levels", ("proficiency_levels", "proficiency levels")),
    ResumeField(
        "certification providers",
        ("certification_providers", "certification providers"),
    ),
    ResumeField(
        "certification skills",
        ("certification_skills", "certification skills"),
    ),
    ResumeField("online links", ("online_links", "online links")),
    ResumeField("issue dates", ("issue_dates", "issue dates")),
    ResumeField("expiry dates", ("expiry_dates", "expiry dates")),
    ResumeField("address", ("address",)),
)


def build_vacancy_text(row: dict[str, str], key_map: dict[str, str]) -> tuple[str, str]:
    title = get_value(row, key_map, "Job Title", "title")
    description = get_value(row, key_map, "Job Description", "description", "text")
    return clean_text(title), clean_text(description)


def build_resume_text(row: dict[str, str], key_map: dict[str, str]) -> str:
    sections: list[str] = []
    for field in RESUME_FIELDS:
        raw_value = get_value(row, key_map, *field.aliases)
        parsed = parse_maybe_list(raw_value)
        cleaned = clean_text(parsed)
        if cleaned:
            sections.append(f"{field.label}: {cleaned}")
    return "\n".join(sections).strip()


def write_jsonl(path: Path, records: Iterable[dict[str, str]]) -> int:
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1
    return count


def build_vacancy_records(rows: list[dict[str, str]], key_map: dict[str, str]) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for idx, row in enumerate(rows, start=1):
        title, text = build_vacancy_text(row, key_map)
        if not text:
            continue
        records.append({"id": f"job_{idx:06d}", "title": title, "text": text})
    return records


def build_resume_records(rows: list[dict[str, str]], key_map: dict[str, str]) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for idx, row in enumerate(rows, start=1):
        text = build_resume_text(row, key_map)
        if not text:
            continue
        records.append({"id": f"resume_{idx:06d}", "text": text})
    return records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build parsed vacancies/resumes JSONL.")
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=Path("data/raw"),
        help="Directory containing source CSV files.",
    )
    parser.add_argument(
        "--parsed-dir",
        type=Path,
        default=Path("data/parsed"),
        help="Directory where JSONL output files will be written.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    raw_dir: Path = args.raw_dir
    parsed_dir: Path = args.parsed_dir

    vacancy_path = raw_dir / VACANCY_FILENAME
    resume_path = raw_dir / RESUME_FILENAME

    if not vacancy_path.exists():
        raise FileNotFoundError(f"Missing vacancy source file: {vacancy_path}")
    if not resume_path.exists():
        raise FileNotFoundError(f"Missing resume source file: {resume_path}")

    parsed_dir.mkdir(parents=True, exist_ok=True)

    vacancy_rows, vacancy_keys = read_rows(vacancy_path)
    resume_rows, resume_keys = read_rows(resume_path)

    vacancy_records = build_vacancy_records(vacancy_rows, vacancy_keys)
    resume_records = build_resume_records(resume_rows, resume_keys)

    vacancies_jsonl = parsed_dir / "vacancies.jsonl"
    resumes_jsonl = parsed_dir / "resumes.jsonl"

    vacancy_count = write_jsonl(vacancies_jsonl, vacancy_records)
    resume_count = write_jsonl(resumes_jsonl, resume_records)

    ratio = (resume_count / vacancy_count) if vacancy_count else 0.0
    print(f"Wrote {vacancy_count} vacancies to {vacancies_jsonl}")
    print(f"Wrote {resume_count} resumes to {resumes_jsonl}")
    print(f"Resume-to-vacancy ratio: {ratio:.2f} resumes/job")


if __name__ == "__main__":
    main()
