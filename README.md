# Job-Resume Matching MVP

Simple end-to-end MVP for matching resumes to a job description using a trained XGBoost ranker.

## What this project does

1. Accepts a job title and job description.
2. Loads local candidate resumes from a JSON file.
3. Builds lightweight ranking features.
4. Runs a trained XGBoost ranking model.
5. Returns top candidates with:
   - baseline score/rank
   - ML score/rank
   - short explanation

This project is intentionally MVP-sized:

## Project structure

- `backend/app/api` -> FastAPI routes (`/health`, `/rank-candidates`, `/match-job`)
- `backend/app/services` -> business logic (ranking, feature building, matching flow)
- `backend/app/config` -> constants and local paths
- `backend/app/repositories` -> local candidate loading
- `backend/app/schemas` -> request/response models
- `backend/data/candidates.json` -> local demo candidate dataset
- `backend/examples/*.json` -> example request payloads
- `backend/scripts/demo_match_job.py` -> human-readable demo runner
- `models/ranker_model.json` -> trained ranker artifact
- `data/train_ranker.py` -> model training script (already completed)

## Quick start

## 1) Create and activate virtual environment

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

## 2) Install minimal dependencies

```powershell
pip install fastapi uvicorn pandas xgboost
```

## 3) Run API

From repository root:

```powershell
python backend/run_api.py
```

API will run on `http://127.0.0.1:8000`.

## Main endpoints

- `GET /health`
- `POST /rank-candidates` (precomputed features in request)
- `POST /match-job` (full local MVP flow)

Interactive docs:
- `http://127.0.0.1:8000/docs`

## Demo the full flow (`/match-job`)


## Notes

- The ranker model is loaded from `models/ranker_model.json`.
- Candidate data is local file-based (`backend/data/candidates.json`).
- If you change candidate data, rerun the same `/match-job` request to see ranking changes.

