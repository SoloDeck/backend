.PHONY: help install dev up down logs migrate revision test lint fmt typecheck clean

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
migrate: ## Apply pending Alembic migrations
	alembic upgrade head

revision: ## Create a new Alembic migration (use: make revision msg="describe change")
	alembic revision --autogenerate -m "$(msg)"

downgrade: ## Rollback one migration
	alembic downgrade -1

db-shell: ## Open psql shell
	docker compose exec db psql -U solodesk -d solodesk

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
