FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app \
    HF_HOME=/app/.cache/huggingface

WORKDIR /app

# libgomp1 = lightgbm. curl for healthcheck. build-essential only needed for any wheel
# that has to compile from source (most are prebuilt — keep for safety).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libgomp1 \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --upgrade pip \
    && pip install -r /app/backend/requirements.txt

# Pre-download the cross-encoder so first /shortlist request doesn't stall on HF fetch (~500MB).
ARG CROSS_ENCODER_MODEL=cross-encoder/ms-marco-MiniLM-L-12-v2
RUN python -c "from sentence_transformers import CrossEncoder; CrossEncoder('${CROSS_ENCODER_MODEL}')"

COPY backend /app/backend
COPY src /app/src

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=8 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# Single worker on purpose: the cross-encoder + LightGBM artifacts each take ~500MB,
# and a second worker would duplicate them in RAM (or VRAM on GPU). Concurrent
# requests are still handled via FastAPI's async loop + threadpool.
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
