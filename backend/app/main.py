from __future__ import annotations

from fastapi import FastAPI

from backend.app.api import router as api_router

app = FastAPI(title="Job-Resume Ranking MVP", version="0.1.0")
app.include_router(api_router)

