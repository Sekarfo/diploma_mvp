# Backend MVP Demo

This backend supports a local end-to-end matching flow with no database:

1. Receive `job_title` + `job_description`
2. Load local candidates from `backend/data/candidates.json`
3. Build ranking features
4. Compare baseline heuristic ranking vs ML reranking
5. Return top candidates from `/match-job`

## Run the backend

From the repository root:

```bash
python backend/run_api.py
```

API will be available at `http://127.0.0.1:8000`.

## Run demo request (curl)

```bash
curl -X POST "http://127.0.0.1:8000/match-job" ^
  -H "Content-Type: application/json" ^
  --data @backend/examples/match_job_request.json
```

## Run demo script (human-readable output)

```bash
python backend/scripts/demo_match_job.py
```

Optional arguments:

```bash
python backend/scripts/demo_match_job.py --base-url http://127.0.0.1:8000 --request-file backend/examples/match_job_request.json
```

## What to expect in output

Each candidate includes:

- `baseline_score` and `baseline_rank` (simple heuristic before ML)
- `model_score` and `model_rank` (XGBoost reranker)
- `explanation` (lightweight text from matched skills, overlap, title overlap, estimated years)

This makes live demos easy: you can show how ML reranking changes ordering relative to baseline.

