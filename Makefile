.PHONY: help install dev up down logs migrate revision migrate-docker seed-docker db-init seed bootstrap reset-db test test-unit test-integration test-fast test-build lint fmt typecheck check agent-check agent-db-check clean

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
# Testing (all targets run inside Docker via the 'test' service)
# ---------------------------------------------------------------------------
test-build: ## Build the test Docker image
	docker compose build test

test: ## Run full test suite (Docker)
	docker compose run --rm test python -m pytest tests/ -v --cov=src --cov-report=term-missing

test-unit: ## Run unit tests only (Docker)
	docker compose run --rm test python -m pytest tests/unit/ -v

test-integration: ## Run integration tests only (Docker)
	docker compose run --rm test python -m pytest tests/integration/ -v

test-fast: ## Run tests, stop on first failure (Docker)
	docker compose run --rm test python -m pytest tests/ -x -q

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

agent-check: ## Fast non-mutating gate for AI agents (contract + lint + type + unit tests)
	python scripts/agent_check.py
	ruff check src tests scripts
	mypy src
	pytest tests/unit -v

agent-db-check: ## DB-dependent gate for AI agents (migrate/seed + integration tests)
	docker compose up -d db
	docker compose run --rm migrate python scripts/bootstrap.py
	pytest tests/integration -v

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
clean: ## Remove __pycache__, .pyc, .coverage, .mypy_cache
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -name "*.pyc" -delete
	rm -rf .coverage .mypy_cache .ruff_cache htmlcov
