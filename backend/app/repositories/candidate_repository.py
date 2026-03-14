from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from backend.app.config import CANDIDATES_DATA_PATH


class LocalCandidateRepository:
    """Loads candidate profiles from a local JSON file."""

    def __init__(self, data_path: str | Path = CANDIDATES_DATA_PATH) -> None:
        self.data_path = Path(data_path)

    def load_candidates(self) -> pd.DataFrame:
        if not self.data_path.exists():
            raise FileNotFoundError(f"Candidate data file not found: {self.data_path}")

        raw = json.loads(self.data_path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError("Candidate data file must contain a JSON array.")

        df = pd.DataFrame(raw)
        required_columns = ["resume_id", "resume_text"]
        missing = [col for col in required_columns if col not in df.columns]
        if missing:
            raise ValueError(
                "Candidate data is missing required columns: " + ", ".join(missing)
            )

        if df.empty:
            raise ValueError("Candidate data file is empty.")

        return df

