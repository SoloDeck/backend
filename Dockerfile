# ===========================================================================
# SoloDesk Backend — Multi-stage Dockerfile
# ===========================================================================

# ---------------------------------------------------------------------------
# Stage 1: dependency builder
# ---------------------------------------------------------------------------
FROM python:3.13-slim AS builder

WORKDIR /build

COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /uvx /usr/local/bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --frozen --no-dev


# ---------------------------------------------------------------------------
# Stage 2: runtime
# ---------------------------------------------------------------------------
FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PATH="/opt/venv/bin:${PATH}"

WORKDIR /app

# Non-root user
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

# System libraries required by WeasyPrint (PDF rendering)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libffi8 \
    shared-mime-info \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages
COPY --from=builder /opt/venv /opt/venv

# Copy source
COPY src ./src
COPY contracts ./contracts
COPY alembic ./alembic
COPY alembic.ini .
COPY scripts ./scripts

RUN chown -R appuser:appgroup /app
USER appuser

ARG API_PORT=8000
ENV PORT=${API_PORT}

EXPOSE ${PORT}

CMD ["sh", "-c", "uvicorn src.main:app --host 0.0.0.0 --port ${PORT}"]


# ---------------------------------------------------------------------------
# Stage 3: celery worker (same image, different CMD)
# ---------------------------------------------------------------------------
FROM runtime AS worker

CMD ["celery", "-A", "src.infrastructure.celery.app.celery_app", "worker", \
     "--loglevel=info", "--concurrency=4"]


# ---------------------------------------------------------------------------
# Stage 4: celery beat scheduler
# ---------------------------------------------------------------------------
FROM runtime AS beat

CMD ["celery", "-A", "src.infrastructure.celery.app.celery_app", "beat", \
     "--loglevel=info", "--scheduler=celery.beat:PersistentScheduler"]


# ---------------------------------------------------------------------------
# Stage 5: dev / test — installs [dev] extras (pytest, httpx, mypy, ruff…)
# Tests directory is mounted via docker-compose volume, not baked in.
# ---------------------------------------------------------------------------
FROM python:3.13-slim AS test

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:${PATH}"

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /uvx /usr/local/bin/

COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --frozen --extra dev

COPY src ./src
COPY contracts ./contracts
COPY alembic ./alembic
COPY alembic.ini .
COPY scripts ./scripts
