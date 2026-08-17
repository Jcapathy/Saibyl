FROM python:3.12-slim AS builder
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

FROM python:3.12-slim
WORKDIR /app

# System deps: ffmpeg (video processing), WeasyPrint (PDF export), curl (healthcheck)
#
# The font packages are not optional. `python:3.12-slim` ships **zero** fonts —
# `find /usr/share/fonts -type f` returns nothing — so WeasyPrint had nothing to
# set the exported report in. Liberation covers the document's serif/sans/mono
# stack with Arial- and Times-compatible metrics; DejaVu is the per-glyph
# fallback that carries the typographic characters the report actually uses
# (U+2212 minus in every figure, en/em dashes, curly quotes, the middot in the
# page furniture).
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    fonts-liberation \
    fonts-dejavu-core \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -s /bin/bash appuser

COPY --chown=appuser:appuser --from=builder /app/.venv .venv

# Chromium for Playwright (website capture, PRD V3 §4a). Installed here, as
# root, at a fixed shared path: Playwright's default download location is
# per-user (~/.cache), so leaving installation to runtime would mean `appuser`
# re-downloading a browser measured in hundreds of MB on every container start.
# Baking it into the image at a root-owned path — before USER appuser — makes
# it a one-time build cost; `--with-deps` adds the shared libraries chromium
# needs on a slim image, and the chmod lets the non-root runtime user read and
# execute what root installed. Placed before the app/ COPY so code changes
# don't invalidate this layer.
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN /app/.venv/bin/playwright install --with-deps chromium && chmod -R a+rX /ms-playwright

COPY --chown=appuser:appuser app/ app/
COPY --chown=appuser:appuser scripts/ scripts/
COPY --chown=appuser:appuser data/ data/

USER appuser

ENV PATH="/app/.venv/bin:$PATH"

# Render assigns $PORT (default 10000); fall back to 8000 for local
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1
