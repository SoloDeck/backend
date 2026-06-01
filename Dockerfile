# ===========================================================================
# SoloDesk Backend — Multi-stage Dockerfile
# ===========================================================================

# ---------------------------------------------------------------------------
# Stage 1: dependency builder
# ---------------------------------------------------------------------------
FROM python:3.13-slim AS builder

WORKDIR /build

RUN pip install --no-cache-dir hatch

COPY pyproject.toml .
RUN pip install --no-cache-dir --prefix=/install --ignore-installed .


# ---------------------------------------------------------------------------
# Stage 2: runtime
# ---------------------------------------------------------------------------
FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# Non-root user
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

# Copy installed packages
COPY --from=builder /install /usr/local

# Copy source
COPY src ./src
COPY contracts ./contracts
COPY alembic ./alembic
COPY alembic.ini .
COPY scripts ./scripts

RUN chown -R appuser:appgroup /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]


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
