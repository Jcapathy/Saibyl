FROM python:3.12-slim AS builder
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

FROM python:3.12-slim
WORKDIR /app

# System deps: ffmpeg (video processing), WeasyPrint (PDF export), curl (healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/.venv .venv
COPY app/ app/
COPY scripts/ scripts/
COPY data/ data/

RUN useradd -m -s /bin/bash appuser
USER appuser

ENV PATH="/app/.venv/bin:$PATH"

# Render assigns $PORT (default 10000); fall back to 8000 for local
# --limit-max-request-size=52428800 enforces 50MB global request body limit
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --limit-max-request-size 52428800
