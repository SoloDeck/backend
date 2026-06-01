# SoloDesk Backend AI Agent Instructions

You are a senior software architect and backend engineer working on SoloDesk.

## Project Overview

SoloDesk is an AI-powered CRM and deal management platform for Vietnamese freelancers.

Main business domains:

* Authentication
* Users
* Subscriptions
* Clients
* Deals
* Contracts
* Proposals
* Invoices
* Reminders
* Analytics
* Admin
* AI Automation

The backend stack is:

* Python 3.13
* FastAPI
* PostgreSQL 16
* SQLAlchemy 2.x async
* Alembic (async migrations)
* Redis 7
* Celery 5 + beat
* LangChain + OpenAI (gpt-4o)
* Pydantic v2
* structlog

Key reference documents:

* `CLAUDE.md` — full coding rules, CORRECT/WRONG examples, common mistakes
* `docs/domains/INDEX.md` — domain catalog, dependency graph, ownership matrix
* `docs/domains/aggregates/` — DDD aggregate design per domain
* `docs/adr/` — architectural decision records
* `.ai/` — agent-specific rules for architecture, coding, naming, testing

---

## Architecture Style

Use Modular Monolith Architecture.

DO NOT organize code by technical layers at project root.

BAD:
```
controllers/
services/
repositories/
```

GOOD:
```
modules/
  deals/
  clients/
  contracts/
  reminders/
```

Each module owns its API, application, domain and infrastructure code.

---

## Module Structure

Each module must follow:

```
modules/<module_name>/
├── api/
│   └── router.py
├── application/
│   └── service.py
├── domain/
│   └── entities.py
├── infrastructure/
│   ├── models.py
│   └── repository.py
└── schemas/
    ├── request.py
    └── response.py
```

---

## Dependency Rules

Allowed:
```
API → Application → Domain
                 → Infrastructure (Repository)
                 → AIFacade
                 → EventBus
```

Forbidden:
```
API → Repository          (skip service layer)
Repository → Service      (reverse dependency)
Domain → SQLAlchemy       (domain must be pure Python)
Modules → langchain       (must use AIFacade)
Service → HTTPException   (use domain exceptions only)
```

---

## Architecture Guardrails

These rules are non-negotiable. Violating any of them requires an explicit ADR:

* **Never bypass the Application layer.** All business rules live in `service.py`. Routers call services. Repositories are never called directly from routers.
* **Never access repositories from the API layer.** `router.py` files must not import or instantiate repository classes.
* **Never place business logic inside SQLAlchemy models.** ORM models are data containers only — no `if/else`, no validation, no state transitions.
* **Never call OpenAI or LangChain directly outside `src/ai/`.** All LLM access goes through `AIFacade`.
* **Never raise `HTTPException` inside a service.** Raise domain exceptions (`NotFoundError`, `BusinessRuleError`, etc.) — the HTTP handler in `shared/exceptions/http.py` translates them.
* **Never skip `WHERE deleted_at IS NULL`** on soft-deletable tables (`users`, `clients`, `deals`).
* **Never skip `WHERE owner_user_id = :uid`** on user-scoped tables. Missing this filter leaks another user's data.
* **Never update append-only tables** (`client_communication_logs`, `deal_activity_entries`, `invoice_payment_records`, `reminder_delivery_records`, `billing_events`, `audit_log_entries`).
* **Never apply AI output directly to a non-draft record.** AI-generated content is always a `draft` — the user must explicitly confirm/send.

---

## Business Logic Rules

Business rules belong only in the Application layer (`service.py`).

Repositories contain data access only — no `if`, no validation, no state conditions.

No business logic in routers.

No business logic in SQLAlchemy models.

Domain entities encode invariants as pure Python methods (e.g., `Deal.can_transition_to()`).

---

## AI Rules

All AI-related functionality belongs under `src/ai/`.

Never place LangChain logic inside business modules.

Business modules must call `AIFacade` only:

```
DealService → AIFacade → LeadQualifierChain
ProposalService → AIFacade → ProposalGeneratorChain
```

Entitlement check (`subscription.can_use_ai`) is always first, inside AIFacade.

All AI calls log to `ai_cost_records` — always, even on failure.

---

## Testing Rules

Every Application Service method requires:
* Unit tests (mocked repository, no DB)
* Integration tests (real DB, ASGI test client)

AI chains require:
* Prompt rendering tests
* Output parser tests with fixture strings
* No real OpenAI calls in tests

---

## Coding Standards

* Type hints everywhere — `mypy --strict` must pass.
* `async def` for all service and repository methods.
* Dependency injection via FastAPI `Depends()`.
* Pydantic v2 for all schemas.
* `model_config = {"from_attributes": True}` on response schemas.
* Follow Ruff linting rules.
* Follow Black formatting (line length 100).

---

## Definition Of Done

A feature is complete **only when all of the following are true**:

- [ ] Domain entity updated (`domain/entities.py`)
- [ ] SQLAlchemy model updated (`infrastructure/models.py`)
- [ ] Alembic migration created and applied
- [ ] Repository method added (`infrastructure/repository.py`)
- [ ] Service method added with full business logic (`application/service.py`)
- [ ] Request/response schemas added (`schemas/`)
- [ ] API router endpoint added (`api/router.py`)
- [ ] OpenAPI contract updated (`contracts/openapi.yaml`)
- [ ] Unit tests added (`tests/unit/`)
- [ ] Integration tests added (`tests/integration/`)
- [ ] `docs/database/schema.sql` updated if table structure changed

---

## Review Checklist

Before submitting code, verify:

**Architecture compliance**
- [ ] No business logic in router or model
- [ ] No repository access from router
- [ ] No LangChain imports in `src/modules/`
- [ ] Domain exceptions used (not `HTTPException`) inside services

**Type safety**
- [ ] All function signatures have return types
- [ ] No `Any` without justification
- [ ] Pydantic models validated at boundaries

**Test coverage**
- [ ] Unit test for every new service method
- [ ] Integration test for every new endpoint
- [ ] Edge cases and error paths covered

**OpenAPI alignment**
- [ ] Request body matches `contracts/openapi.yaml`
- [ ] Response schema matches `contracts/openapi.yaml`
- [ ] Status codes match `contracts/openapi.yaml`

**Domain consistency**
- [ ] `owner_user_id` filter present on all user-scoped queries
- [ ] `deleted_at IS NULL` filter on soft-deletable tables
- [ ] Append-only tables never updated
- [ ] State transitions validated before DB write

---

## Refactoring Rules

**Allowed without approval:**
* Internal implementation improvements within a module
* Performance optimizations that don't change public interfaces
* Test coverage improvements
* Typing improvements

**Forbidden without explicit ADR:**
* Domain ownership changes (moving a concept from one module to another)
* Boundary violations (allowing direct cross-module repository access)
* Architectural shortcuts (adding business logic to a router or model)
* Removing the Application layer for "simple" endpoints

---

## Deliverables

When implementing any feature, deliver in this order:

1. Domain entity changes
2. SQLAlchemy model + Alembic migration
3. Repository method(s)
4. Application service method(s)
5. Request/response schemas
6. API router endpoint
7. OpenAPI contract update
8. Unit tests
9. Integration tests

Generate production-grade code. No stubs, no TODOs, no placeholder logic.
