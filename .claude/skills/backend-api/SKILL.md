---
name: backend-api
description: Implement a SoloDesk backend feature with FastAPI + SQLAlchemy 2 async + pydantic 2 + alembic. Use when adding/changing an endpoint, pydantic schema, SQLAlchemy model, alembic migration, or business logic under backend/src/modules (clients, deals, invoices, proposals, contracts, reminders, analytics, auth, users, subscriptions, admin).
---

# Backend API — SoloDesk FastAPI

Stack: FastAPI (standard), SQLAlchemy 2 asyncio, pydantic 2 / pydantic-settings, alembic. It is an AI-powered CRM for Vietnamese freelancers.

## Module structure (mirrors the existing modules)
```
src/modules/{module}/
├── api/             FastAPI router (endpoints)
├── application/     use case / service
├── domain/          entity, business rules
├── infrastructure/  repository, ORM model
└── schemas/         pydantic request/response
```
Shared infrastructure: `src/config`, `src/shared`, `src/infrastructure`, `src/integrations`, `src/ai`, `src/workers`.

## Working principles
- Read `backend/CLAUDE.md`, `backend/AGENTS.md`, `backend/TASK.md`, `backend/TASK-DOMAIN-DOCS.md` before coding.
- Request/response shapes must match `backend/contracts/openapi.yaml`. To change a shape → contract-keeper updates openapi.yaml first, don't change it yourself.
- pydantic v2 patterns; API fields are **snake_case**.
- Fully async: SQLAlchemy `asyncio`, no blocking sync I/O on the event loop.
- Changing an ORM model → create an alembic migration (`alembic revision --autogenerate`), review the diff before applying. Don't drop a column with data without auditing clients.

## Verify
- Run tests (`pytest`) and lint/type (ruff/mypy per `pyproject.toml`); report the real output.
- Migration failure: never drop data, report and propose.

## Boundaries
Edit only files in the `backend/` submodule. Commit into the backend repo; update the submodule pointer in the root repo.
