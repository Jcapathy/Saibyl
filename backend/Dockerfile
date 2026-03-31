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

RUN useradd -m -s /bin/bash appuser

COPY --chown=appuser:appuser --from=builder /app/.venv .venv
COPY --chown=appuser:appuser app/ app/
COPY --chown=appuser:appuser scripts/ scripts/
COPY --chown=appuser:appuser data/ data/

USER appuser

ENV PATH="/app/.venv/bin:$PATH"

# Render assigns $PORT (default 10000); fall back to 8000 for local
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1
