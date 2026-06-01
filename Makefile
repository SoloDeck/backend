.PHONY: help install dev up down logs migrate revision migrate-docker seed-docker db-init seed bootstrap reset-db test lint fmt typecheck clean

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------
help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
install: ## Install all dependencies (including dev)
	pip install -e ".[dev]"

# ---------------------------------------------------------------------------
# Docker
# ---------------------------------------------------------------------------
up: ## Start all services (API, DB, Redis, Worker, Beat, Mailpit)
	docker compose up --build -d

down: ## Stop all services
	docker compose down

logs: ## Tail all service logs
	docker compose logs -f

logs-api: ## Tail API logs only
	docker compose logs -f api

logs-worker: ## Tail Celery worker logs
	docker compose logs -f worker

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
migrate: ## Apply pending Alembic migrations (local, requires local DB)
	alembic upgrade head

revision: ## Create a new Alembic migration (use: make revision msg="describe change")
	alembic revision --autogenerate -m "$(msg)"

downgrade: ## Rollback one migration
	alembic downgrade -1

db-shell: ## Open psql shell inside Docker
	docker compose exec db psql -U solodesk -d solodesk

migrate-docker: ## Apply migrations via Docker (requires: docker compose up -d db)
	docker compose run --rm migrate alembic upgrade head

seed-docker: ## Run seeders via Docker (requires: docker compose up -d db)
	docker compose run --rm migrate python scripts/seed.py

db-init: ## Apply migrations + seed via Docker — full DB init (requires: docker compose up -d db)
	docker compose run --rm migrate python scripts/bootstrap.py

seed: ## Run seeders locally (requires local DB + installed deps)
	python scripts/seed.py

bootstrap: ## Run migrations + seed locally (requires local DB + installed deps)
	python scripts/bootstrap.py

reset-db: ## DROP all tables, re-migrate, re-seed — DESTRUCTIVE, dev/CI only
	python scripts/reset_db.py

# ---------------------------------------------------------------------------
# Development
# ---------------------------------------------------------------------------
dev: ## Run API with hot-reload (local, no Docker)
	uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

worker-dev: ## Run Celery worker locally
	celery -A src.infrastructure.celery.app.celery_app worker --loglevel=debug

beat-dev: ## Run Celery beat locally
	celery -A src.infrastructure.celery.app.celery_app beat --loglevel=debug

# ---------------------------------------------------------------------------
# Testing
# ---------------------------------------------------------------------------
test: ## Run full test suite
	pytest -v --cov=src --cov-report=term-missing

test-unit: ## Run unit tests only
	pytest tests/unit -v

test-integration: ## Run integration tests only
	pytest tests/integration -v

test-fast: ## Run tests, stop on first failure
	pytest -x -q

# ---------------------------------------------------------------------------
# Code quality
# ---------------------------------------------------------------------------
lint: ## Lint with Ruff
	ruff check src tests

fmt: ## Format with Black + Ruff import sort
	black src tests
	ruff check --fix src tests

typecheck: ## Type-check with Mypy
	mypy src

check: lint typecheck ## Run lint + typecheck

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
clean: ## Remove __pycache__, .pyc, .coverage, .mypy_cache
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -name "*.pyc" -delete
	rm -rf .coverage .mypy_cache .ruff_cache htmlcov
