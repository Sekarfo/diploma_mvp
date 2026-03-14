from __future__ import annotations

from pathlib import Path

# backend/app/config/matching.py -> repo root is parents[3]
CANDIDATES_DATA_PATH = Path(__file__).resolve().parents[3] / "backend" / "data" / "candidates.json"

SKILL_KEYWORDS = [
    "python",
    "java",
    "sql",
    "aws",
    "azure",
    "gcp",
    "docker",
    "kubernetes",
    "terraform",
    "fastapi",
    "scikit-learn",
    "pytorch",
    "tensorflow",
    "airflow",
    "spark",
    "kafka",
    "tableau",
    "power bi",
    "amplitude",
    "mixpanel",
    "selenium",
    "playwright",
    "postman",
    "spacy",
    "transformers",
    "mlflow",
    "kubeflow",
    "prometheus",
    "postgresql",
]

