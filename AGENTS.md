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
* WeasyPrint (PDF generation)
* SendGrid (email delivery)
* Zalo Official Account (OA) API (messaging delivery)
* Pydantic v2
* structlog

Key reference documents:

* `CLAUDE.md` — full coding rules, CORRECT/WRONG examples, common mistakes
* `docs/domains/INDEX.md` — domain catalog, dependency graph, ownership matrix
* `docs/domains/aggregates/` — DDD aggregate design per domain
* `docs/adr/` — architectural decision records
* `.ai/` — agent-specific rules for architecture, coding, naming, testing

---

## Agent Workflow

Every task that adds or modifies a feature must follow this sequence:

1. Implement through the proper module layers.
2. Write unit tests for every new or changed service method.
3. Write integration tests for every new or changed API endpoint.
4. Run the relevant tests before considering the task complete.

Never mark a feature complete without corresponding tests unless the task is explicitly
documentation-only, planning-only, or non-code-only.

---

## API Response Standard

**All REST API responses must use the standard envelope. No exceptions.**

### Success — single resource
```json
{ "success": true, "code": 200, "timestamp": "...", "data": {} }
```

### Success — collection
```json
{ "success": true, "code": 200, "timestamp": "...", "data": [], "pagination": {} }
```

### Error — any 4xx / 5xx
```json
{ "success": false, "code": 400, "timestamp": "...", "error": { "message": "...", "code": "VALIDATION_FAILED", "details": [] } }
```

**Use the helpers from `src/shared/responses/`:**
```python
from src.shared.responses import ApiResponse, PaginatedResponse

# Single resource
return ApiResponse.ok(result)          # 200
return ApiResponse.created(result)     # 201

# Collection
return PaginatedResponse.ok(items, total=total, page=page, page_size=page_size)
```

**Forbidden — reviewer will reject immediately:**
```python
return entity                          # raw ORM model
return list_of_items                   # raw list
return {"message": "success"}          # ad-hoc dict
raise HTTPException(...)               # use domain exceptions instead
```

**Required error codes** (defined in `src/shared/responses/error.py` → `ErrorCode`):

| Code | When |
|---|---|
| `VALIDATION_FAILED` | Request schema violation (422) |
| `UNAUTHORIZED` | Missing / invalid token (401) |
| `FORBIDDEN` | Authenticated but not permitted (403) |
| `NOT_FOUND` | Resource not found (404) |
| `CONFLICT` | Duplicate or invalid state (409) |
| `BUSINESS_RULE_VIOLATION` | Domain rule broken (409) |
| `SUBSCRIPTION_REQUIRED` | Plan entitlement missing (402) |
| `AI_QUOTA_EXCEEDED` | AI generation failed / quota (502) |
| `INTERNAL_SERVER_ERROR` | Unhandled exception (500) |

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

## Module Ownership

Keep domain concepts in their owning module:

| Module | Owns | Boundary |
|---|---|---|
| `auth` | Login, Google OAuth, JWTs, refresh tokens, logout, password reset | Does not own user profiles or subscription state |
| `users` | Profile, professional profile, preferences, soft-delete | Does not own credentials, subscriptions, or business records |
| `subscriptions` | Plans, subscription lifecycle, usage counters, billing events, entitlement checks | Does not own raw payment gateway processing |
| `clients` | Client address book, contacts, communication logs, tags, lifecycle | Does not own deals, proposals, contracts, or invoices |
| `deals` | Deal CRUD, pipeline stage transitions, activity log, AI qualification trigger, embeddable intake form (shareable client self-submission link) | Does not own documents or invoices |
| `proposals` | Proposal versions, lifecycle, share links, AI draft trigger | Does not directly advance deal stages |
| `contracts` | Contract creation, draft editing, signing, amendments, payment milestones | Does not own invoice creation or payment tracking |
| `invoices` | Invoice CRUD, line items, tax totals, payment recording, overdue detection, share links | Does not own contract milestone definitions |
| `reminders` | Scheduling, recurrence, delivery records, target lifecycle reactions. Delivery channels: email via SendGrid or Zalo OA message; channel chosen per user preference. | Does not own target business objects |
| `analytics` | Read-only revenue, pipeline, client, subscription, and AI usage metrics | Never writes operational tables |
| `admin` | Admin user management, subscription overrides, templates, feature flags, audit logs, platform metrics | Must not bypass domain services |

Critical module rules:

* `subscriptions` entitlement checks must happen before AI token consumption.
* `deals` pipeline stages (forward-only): `new_lead` → `qualified` → `proposal_sent` → `in_negotiation` → `active` → `completed_and_billed`. `lost` is terminal and reachable from any non-terminal stage.
* `proposals` may have only one `sent` proposal per deal at a time.
* `contracts` embed `client_snapshot` at creation and never read live client data for contract display.
* `invoices` must link to `contract_id` or `deal_id`; standalone invoices are invalid.
* `analytics` is read-only and always scoped by `owner_user_id`.
* `admin` actions must be written to `audit_log_entries`.

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

## Coding Patterns

### Dependency Injection

Services and repositories use `@dataclass` for dependency injection. Repositories are
created in `__post_init__` so tests can pass mocks.

```python
@dataclass
class DealsService:
    db: AsyncSession
    repo: DealsRepository | None = None

    def __post_init__(self) -> None:
        if self.repo is None:
            self.repo = DealsRepository(self.db)
```

Router rules:

* Routers instantiate services directly.
* Use `CurrentUser`, `CurrentUserId`, and `AdminUser` from `src/shared/dependencies/auth.py`.
* Use `DBSession` from `src/shared/dependencies/db.py`.
* Never instantiate `AIFacade` inside a router; inject it into the service.
* A router endpoint parses input, calls one service method, and wraps the response.

### Repositories

Repositories execute SQLAlchemy queries only. They do not validate state, raise HTTP
errors, apply business decisions, or call services.

Always use async SQLAlchemy:

```python
result = await self.db.execute(select(DealModel).where(...))
deal = result.scalar_one_or_none()
```

Never use sync ORM access in async code:

```python
self.db.query(DealModel).filter(...).first()
```

### Schemas

Use Pydantic v2 only.

* `schemas/request.py` validates inbound data with `Field(...)` constraints.
* `schemas/response.py` uses `ConfigDict(from_attributes=True)`.
* Do not put business rules in Pydantic validators.

### Logging and Security

* Use `structlog.get_logger(__name__)`; never use `print()`.
* Password hashing must use `src/shared/security/passwords.py`.
* Use `X | None`; do not use `Optional[X]` in new code.

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

Tests are part of the implementation, not a follow-up task.

Every Application Service method requires:
* Unit tests (mocked repository, no DB)
* Integration tests (real DB, ASGI test client)

AI chains require:
* Prompt rendering tests
* Output parser tests with fixture strings
* No real OpenAI calls in tests

Test locations:

```
tests/
├── conftest.py
├── unit/
│   ├── modules/<name>/test_service.py
│   └── shared/<name>/test_*.py
└── integration/
    └── modules/<name>/test_*_api.py
```

Unit test rules:

* Use `AsyncMock` for repositories.
* Cover success, not-found, wrong owner, invalid state transitions, and every error branch.
* Use `pytest.raises(DomainExceptionClass)` for service error paths.
* Group tests by service method, e.g. `class TestCreate`.

Integration test rules:

* Use real PostgreSQL and `AsyncClient`.
* Do not mock the database.
* Minimum per endpoint: success `200/201`, unauthenticated `401`, not found `404` where applicable, validation `422`, and tenant isolation.
* Assert the response envelope shape (`success`, `code`, `data`, `error`).

Fixtures:

* Use inline dict factories instead of factory-boy.
* Never share mutable state between tests.
* Async fixtures use `@pytest_asyncio.fixture`.

---

## Coding Standards

* Type hints everywhere — `mypy --strict` must pass.
* `async def` for all service and repository methods.
* Dependency injection follows the service `@dataclass` pattern.
* Pydantic v2 for all schemas.
* `model_config = ConfigDict(from_attributes=True)` on response schemas.
* PostgreSQL enum ORM columns use `PgEnum(..., create_type=False)`; Alembic creates enum types.
* Follow Ruff linting rules.
* Follow Black formatting (line length 100).

---

## Database And Migration Rules

* All primary keys are UUIDs generated by PostgreSQL `gen_random_uuid()`.
* Mutable tables include `created_at` and `updated_at`; `updated_at` is maintained by PostgreSQL trigger `set_updated_at()`.
* Soft-deletable tables (`users`, `clients`, `deals`) must always filter `deleted_at IS NULL`.
* User-scoped tables must always filter `owner_user_id`.
* Append-only tables are insert-only: `client_communication_logs`, `deal_activity_entries`, `invoice_payment_records`, `reminder_delivery_records`, `audit_log_entries`, `billing_events`.
* One migration per logical schema change.
* Never edit a committed migration unless the user explicitly asks and it is safe for the current branch.
* Import all SQLAlchemy model files in `alembic/env.py` so autogenerate can detect changes.
* If schema changes, update both Alembic migration and `docs/database/schema.sql`.

---

## Development Workflow

Implement modules in dependency order:

1. infrastructure/database
2. Alembic migrations
3. shared utilities
4. auth
5. users
6. subscriptions
7. clients
8. deals
9. proposals
10. contracts
11. invoices
12. reminders
13. AI chains
14. workers
15. analytics
16. admin

For each module, complete:

```text
domain/entities.py + invariant tests
infrastructure/models.py with PgEnum(..., create_type=False)
infrastructure/repository.py
application/service.py + unit tests
schemas/request.py and schemas/response.py
api/router.py + integration tests
Alembic migration when schema changes
contracts/openapi.yaml update
```

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

**Response envelope compliance**
- [ ] Every endpoint returns `ApiResponse[T]` (single) or `PaginatedResponse[T]` (collection)
- [ ] No raw entity, raw list, or ad-hoc dict returned from any router
- [ ] All error responses use the `ApiError` envelope via `setup_exception_handlers`
- [ ] Error `code` field uses one of the `ErrorCode` enum values
- [ ] 422 validation errors include `details` array with field-level breakdown
- [ ] No `HTTPException` raised anywhere in the codebase — domain exceptions only

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
- [ ] Integration tests assert response envelope shape (`success`, `code`, `data`, `error`)

**OpenAPI alignment**
- [ ] Request body matches `contracts/openapi.yaml`
- [ ] Response uses `ApiResponse` / `PaginatedResponse` / `ApiError` refs in the contract
- [ ] Status codes match `contracts/openapi.yaml`

**Domain consistency**
- [ ] `owner_user_id` filter present on all user-scoped queries
- [ ] `deleted_at IS NULL` filter on soft-deletable tables
- [ ] Append-only tables never updated
- [ ] State transitions validated before DB write

---

## Common Mistakes To Avoid

| Mistake | Correct Approach |
|---|---|
| Returning raw entity/list from a router | Wrap with `ApiResponse.ok(...)` or `PaginatedResponse.ok(...)` |
| Returning ad-hoc dicts | Use typed response schema inside standard envelope |
| Raising `HTTPException` in service | Raise domain exception; HTTP handlers translate |
| Querying DB directly from router | Route through service then repository |
| Calling LangChain/OpenAI from `src/modules/` | Use `AIFacade` |
| Importing another module's repository directly | Use domain events or the owning service boundary |
| Forgetting `owner_user_id` filter | Always scope user data |
| Forgetting `deleted_at IS NULL` | Always hide soft-deleted records |
| Using sync SQLAlchemy | Use async `await session.execute(select(...))` |
| Testing only happy path | Add error, auth, validation, and tenant isolation coverage |
| Mocking DB in integration tests | Use real PostgreSQL |
| Applying AI output to a live record | Save AI output as draft and require user confirmation |

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
