# SoloDesk Backend — Claude Code Context

## Agent Workflow

**Every task that adds or modifies a feature must follow this sequence — no exceptions:**

1. Implement the feature (service → repository → router).
2. Write unit tests for every new/changed service method.
3. Write integration tests for every new/changed API endpoint.
4. Confirm all tests pass before considering the task complete.

**Never mark a task done without corresponding tests.**

---

## Project Overview

**SoloDesk** is an AI-powered CRM and deal management platform for Vietnamese freelancers.
It helps freelancers manage clients, track sales pipelines, generate proposals and contracts
with AI assistance, issue invoices, and automate follow-up reminders.

**Key business flow:**
```
Client → Deal → Proposal → Contract → Invoice
              ↓
        AI Qualification / Generation
              ↓
        Reminders → Analytics
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.13 |
| Web framework | FastAPI (async) |
| ORM | SQLAlchemy 2.x async |
| Database | PostgreSQL 16 |
| Migrations | Alembic (async env) |
| Cache / Queue broker | Redis 7 |
| Task queue | Celery 5 with beat scheduler |
| PDF generation | WeasyPrint |
| Email delivery | SendGrid |
| Messaging delivery | Zalo Official Account (OA) API |
| AI orchestration | LangChain + OpenAI (gpt-4o) |
| Validation | Pydantic v2 |
| Settings | pydantic-settings |
| Logging | structlog |
| Password hashing | pwdlib (Argon2id via `PasswordHash.recommended()`) |
| Testing | pytest + pytest-asyncio (`asyncio_mode = "auto"`) |

---

## Architecture

**Pattern: Modular Monolith.**

Code is organized by business domain, not by technical layer. Every domain is a
self-contained module under `src/modules/<name>/`. No shared service layer exists
across modules — modules communicate via domain events or direct service calls.

```
src/
├── modules/          # 11 business domains (see Module Ownership)
├── ai/               # AI chains — never imported by modules directly
├── workers/          # Celery tasks (ai_jobs, pdf_jobs, reminder_jobs, scheduler)
├── integrations/     # External providers (stripe, google_oauth, openai_client, sendgrid, zalo_oa, momo)
├── infrastructure/   # Database, Redis, Celery app setup
├── shared/           # Pagination, exceptions, events, dependencies, security, logging
└── main.py           # FastAPI app, router registration, lifespan
```

### Module internal layout

```
modules/<name>/
├── api/
│   └── router.py         ← HTTP boundary only. No business logic.
├── application/
│   └── service.py        ← All business rules live here.
├── domain/
│   └── entities.py       ← Pure Python dataclasses. No I/O, no SQLAlchemy.
├── infrastructure/
│   ├── models.py         ← SQLAlchemy ORM models.
│   └── repository.py     ← DB queries only. No business logic.
└── schemas/
    ├── request.py        ← Pydantic request bodies.
    └── response.py       ← Pydantic response models.
```

### Allowed dependency directions

```
api/router  →  application/service  →  domain/entities
                                    →  infrastructure/repository
                                    →  ai/facade (via DI)
                                    →  shared/events/bus
```

**Forbidden:**
- `api/router` → `infrastructure/repository` (skip the service layer)
- `infrastructure/repository` → `application/service` (reverse dependency)
- Any module → `langchain` / `openai` directly (must go through AIFacade)
- `domain/entities` → SQLAlchemy / database (domain must be pure)

---

## Module Ownership

### `auth`
**Responsibilities:** credential login, Google OAuth, JWT issuance, refresh token
lifecycle, logout + token blacklisting, password reset.
**Boundaries:** does NOT own user profile data (Users), subscription tier (Subscriptions).
**Depends on:** Users (read user by email), Subscriptions (embed tier in JWT).

### `users`
**Responsibilities:** user account CRUD, professional profile, preferences, soft-delete.
**Boundaries:** does NOT own auth credentials, subscription data, or any business records.
**Depends on:** nothing (leaf domain — all others reference it).

### `subscriptions`
**Responsibilities:** plan catalog, user subscription lifecycle, usage counters, billing events, entitlement checks.
**Boundaries:** does NOT own payment gateway processing (Stripe sends webhooks; we store outcomes only).
**Depends on:** Users (one subscription per user).
**Key rule:** every AI feature check must call `SubscriptionsService.check_entitlement(user_id, "can_use_ai")` before consuming tokens.

### `clients`
**Responsibilities:** client address book, contact info, communication logs, tags, status lifecycle.
**Boundaries:** does NOT own deals, proposals, contracts, or invoices.
**Depends on:** Users (owner_user_id).
**Key rule:** client email is unique per owner user, not globally.

### `deals`
**Responsibilities:** deal CRUD, pipeline stage transitions, activity log, AI qualification trigger, embeddable intake form (shareable link for client self-submission).
**Boundaries:** does NOT own proposal documents, contract documents, invoices, or reminders.
**Depends on:** Clients (client_id immutable after creation).
**Pipeline stages (forward-only):** `new_lead` → `qualified` → `proposal_sent` → `in_negotiation` → `active` → `completed_and_billed`. Terminal stages: `completed_and_billed`, `lost`.
**Key rule:** Validate all transitions using `Deal.can_transition_to()` in the service layer. Moving to `lost` or `completed_and_billed` sets `closed_at` and auto-cancels pending Reminders.

### `proposals`
**Responsibilities:** proposal versioning, lifecycle (draft → sent → accepted/rejected/expired), shareable client link, AI generation trigger.
**Boundaries:** does NOT advance deal stages directly — emits `proposals.proposal_accepted` event.
**Depends on:** Deals (deal_id immutable).
**Key rule:** only one proposal per deal may be `sent` at any time; creating a new revision supersedes the previous.

### `contracts`
**Responsibilities:** contract creation from accepted proposal, content editing (draft only), signing workflow, amendment versioning, payment milestones.
**Boundaries:** does NOT own invoice creation — emits milestone events for Invoices to consume.
**Depends on:** Proposals (proposal must be `accepted`), Deals, Clients.
**Contract scope:** contracts are simple service agreements ("hợp đồng dịch vụ đơn giản") — **not** formal legal documents. AI generation produces a practical working agreement suitable for Vietnamese freelancer–client relationships, not court-enforceable legal text.
**Key rule:** client data is embedded by value at creation (`client_snapshot` JSONB) — never read live client record for contract display.

### `invoices`
**Responsibilities:** invoice CRUD, line items, tax calculation, payment recording, overdue detection, shareable client link.
**Boundaries:** does NOT own contract milestone definitions.
**Depends on:** Clients, Contracts (nullable), Deals.
**Key rules:**
- An invoice must have `contract_id` OR `deal_id` (or both) — never standalone.
- `total = subtotal + tax_amount` validated before `sent` status.
- `amount_paid` cannot exceed `total`.

### `reminders`
**Responsibilities:** reminder scheduling, delivery via Workers, recurrence, auto-cancel when target reaches terminal state.
**Boundaries:** does NOT own business objects — targets them via polymorphic (`target_type`, `target_id`).
**Depends on:** Users (timezone/preferences), Workers (Celery delivery).
**Delivery channels:** email via SendGrid (`src/integrations/sendgrid/`) or Zalo OA message via Zalo API (`src/integrations/zalo_oa/`). Channel is chosen per user preference. Never deliver via raw SMTP or direct HTTP calls — always go through the integration adapters.
**Key rule:** no DB-level FK on `target_id` — referential integrity enforced at application layer.

### `analytics`
**Responsibilities:** revenue snapshots, pipeline snapshots, win rate, top clients, AI usage metrics — all read-only derived data.
**Boundaries:** NEVER writes to operational tables. NEVER owns source-of-truth for any metric.
**Depends on:** reads from Deals, Invoices, Clients, Subscriptions (via queries or events).
**Key rule:** all analytics are scoped to `owner_user_id`. Cross-user data never exposed.

### `admin`
**Responsibilities:** user management, subscription overrides, system templates, feature flags, AI cost monitoring, audit log, platform metrics.
**Boundaries:** reads across all domains but writes only via other domain services (never bypasses them).
**Depends on:** all modules (read-only cross-domain access).
**Key rule:** every admin action is written to `audit_log_entries`. Admin endpoints require `role: admin` claim in JWT.

---

## Coding Rules

### Modern Python Conventions

- Use `X | None` — never `Optional[X]` (Python 3.13 project).
- All functions and methods must have full type annotations.
- Use `structlog.get_logger(__name__)` for logging. Never use `print()`.
- Use `async def` for all DB-touching functions; `def` for pure logic helpers.
- Pydantic v2: use `model_config = ConfigDict(from_attributes=True)` in response schemas.
- ORM models: declare PostgreSQL ENUM columns with `PgEnum(..., create_type=False)` — the ENUM types are created by Alembic migrations, not the ORM.

### Dependency Injection Pattern

Services and repositories use `@dataclass` for DI. Repositories are wired in `__post_init__` so they can be replaced with mocks in tests.

```python
@dataclass
class DealsService:
    db: AsyncSession
    repo: DealsRepository | None = None

    def __post_init__(self) -> None:
        if self.repo is None:
            self.repo = DealsRepository(self.db)
```

Routers instantiate services directly — no FastAPI `Depends` wrapper around services:

```python
@router.post("/", response_model=DealResponse, status_code=201)
async def create_deal(
    body: CreateDealRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> DealResponse:
    service = DealsService(db=db)
    deal = await service.create(body, owner_user_id=user_id)
    return DealResponse.model_validate(deal)
```

Rules:
- All services are `@dataclass` with `db: AsyncSession` as the first field.
- Never instantiate `AIFacade` inside a router — inject it into the service.
- Import the `EventBus` singleton directly in services: `from src.shared.events.bus import event_bus`.
- Password hashing: always use `src/shared/security/passwords.py` — `hash_password()` / `verify_password()`.

### Response Envelope

**Every endpoint must return the standard envelope. Never return raw objects, raw lists, or ad-hoc dicts.**

```python
from src.shared.responses import ApiResponse, PaginatedResponse

# Single resource — 200
return ApiResponse.ok(DealResponse.model_validate(deal))

# Created — 201
return ApiResponse.created(DealResponse.model_validate(deal))

# Collection with pagination
return PaginatedResponse.ok(items, total=total, page=page, page_size=page_size)
```

Error responses are handled automatically by `setup_exception_handlers` in `shared/exceptions/http.py`.
Raise domain exceptions in services; the handler wraps them in `ApiError`.

**Forbidden:**
```python
return deal                        # raw ORM model
return items                       # raw list
return {"message": "ok"}           # ad-hoc dict
raise HTTPException(404, ...)      # use NotFoundError instead
```

**Required error codes** (`src/shared/responses/error.py` → `ErrorCode`):
`VALIDATION_FAILED` · `UNAUTHORIZED` · `FORBIDDEN` · `NOT_FOUND` · `CONFLICT` ·
`BUSINESS_RULE_VIOLATION` · `SUBSCRIPTION_REQUIRED` · `AI_QUOTA_EXCEEDED` · `INTERNAL_SERVER_ERROR`

### Routers (`api/router.py`)
- Parse and validate HTTP input only.
- Call one application service method per endpoint.
- Return `ApiResponse[T]` or `PaginatedResponse[T]` — no domain logic.
- Use `CurrentUser`, `CurrentUserId`, `AdminUser` from `src/shared/dependencies/auth.py`.
- Use `DBSession` from `src/shared/dependencies/db.py`.

```python
# CORRECT
@router.post("/{deal_id}/stage-transition", response_model=ApiResponse[DealResponse])
async def transition_stage(
    deal_id: uuid.UUID,
    body: StageTransitionRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[DealResponse]:
    service = DealsService(db=db)
    deal = await service.transition_stage(deal_id, body.target_stage, user_id)
    return ApiResponse.ok(DealResponse.model_validate(deal))

# WRONG — raw return and business logic in router
@router.post("/{deal_id}/stage-transition")
async def transition_stage(...):
    if deal.stage == "lost":
        raise HTTPException(...)  # ← use InvalidStateTransitionError in the service
    return deal                   # ← wrap in ApiResponse.ok(...)
```

### Services (`application/service.py`)
- Enforce ALL business rules.
- Validate state transitions, ownership, preconditions.
- Call repositories for persistence.
- Call `AIFacade` (injected) for AI features.
- Emit domain events via `EventBus`.
- Raise domain exceptions (`NotFoundError`, `BusinessRuleError`, etc.) — never `HTTPException`.

```python
# CORRECT
async def transition_stage(self, deal_id, target_stage, user_id):
    deal = await self.repo.get_by_id(deal_id, owner_user_id=user_id)
    if deal is None:
        raise NotFoundError(f"Deal {deal_id} not found")
    if not deal.can_transition_to(target_stage):
        raise InvalidStateTransitionError("deal", deal.stage, target_stage)
    ...
```

### Repositories (`infrastructure/repository.py`)
- Execute SQLAlchemy queries only.
- Accept and return domain entities or ORM models — never HTTP types.
- No `if`, no validation, no business conditions.
- Always filter by `owner_user_id` on user-scoped tables.
- Always add `WHERE deleted_at IS NULL` on soft-deletable tables.

```python
# CORRECT
async def get_by_id(self, deal_id: uuid.UUID, owner_user_id: uuid.UUID) -> Deal | None:
    result = await self.db.execute(
        select(DealModel)
        .where(DealModel.id == deal_id)
        .where(DealModel.owner_user_id == owner_user_id)
        .where(DealModel.deleted_at.is_(None))
    )
    return result.scalar_one_or_none()

# WRONG — business logic in repository
async def get_by_id(self, deal_id, owner_user_id):
    deal = await ...
    if deal.stage == "lost":   # ← never
        raise SomeError(...)
```

### Domain Entities (`domain/entities.py`)
- Pure Python dataclasses. Zero imports from SQLAlchemy, FastAPI, or external libs.
- Encode business invariants as methods (e.g. `can_transition_to()`).
- Immutable where appropriate (`frozen=True`).

### Schemas (`schemas/`)
- Pydantic v2 models only.
- `request.py` — validate inbound data; use `Field(...)` for constraints.
- `response.py` — `model_config = ConfigDict(from_attributes=True)` so ORM models map cleanly.
- Never put business logic in validators.

---

## AI Rules

1. **Never import `langchain` or `openai` from any module under `src/modules/`.**
2. All AI access goes through `src/ai/facade.py` → `AIFacade`.
3. `AIFacade` is injected into services via dependency injection — never instantiated inside a router.
4. Entitlement check happens inside `AIFacade.qualify_lead()` / `.generate_proposal()` etc. before any LLM call.
5. AI modules (`src/ai/<module>/chain.py`) return structured `dict` output only. The calling service writes the result to the database.
6. AI-generated content is always a **draft**. The user must explicitly confirm/send before status changes.
7. All generation calls are logged to `ai_cost_records` regardless of outcome.

```python
# CORRECT — in DealsService
result = await self.ai_facade.qualify_lead(
    deal_data=deal_to_dict(deal),
    client_data=client_to_dict(client),
    user_can_use_ai=subscription.can_use_ai,
)

# WRONG — direct LangChain call from a business module
from langchain_openai import ChatOpenAI  # ← forbidden in modules/
```

---

## Database Rules

### Primary Keys
All tables use `UUID` generated by PostgreSQL `gen_random_uuid()`. Use `UUIDMixin` from
`src/infrastructure/database/base.py`.

### Audit Fields
All mutable tables include `created_at` and `updated_at` via `TimestampMixin`.
`updated_at` is managed by a PostgreSQL trigger (`set_updated_at()`), not by the ORM.

### Soft Delete
Tables that support soft delete use `SoftDeleteMixin` (`deleted_at TIMESTAMPTZ NULL`).
Applies to: `users`, `clients`, `deals`.

**Every query on soft-deletable tables must include:**
```python
.where(Model.deleted_at.is_(None))
```

### Append-Only Tables
These tables have `created_at` only (no `updated_at`). Never `UPDATE` them:
- `client_communication_logs`
- `deal_activity_entries`
- `invoice_payment_records`
- `reminder_delivery_records`
- `audit_log_entries`
- `billing_events`

### Multi-Tenancy
Every user-scoped query must filter by `owner_user_id`. No exceptions. This is the
primary isolation guarantee — there is no row-level security at the DB level.

### Async SQLAlchemy
Always use `async with session` / `await session.execute(...)`. Never call synchronous
SQLAlchemy methods in async context.

```python
# CORRECT
result = await self.db.execute(select(DealModel).where(...))
deal = result.scalar_one_or_none()

# WRONG
deal = self.db.query(DealModel).filter(...).first()  # sync — blocks event loop
```

### Migrations
- `make revision msg="describe change"` — auto-generate migration from model diff.
- `make migrate` — apply to database.
- Import all model files in `alembic/env.py` for auto-detect to work.
- One migration per logical change. Never edit a committed migration.
- ORM ENUM columns: `PgEnum("val1", "val2", name="type_name", create_type=False)`.

---

## Testing Rules

Tests are **not optional** — they are part of the implementation. Write them in the same
task, not afterward.

### File locations

```
tests/
├── conftest.py                          ← shared fixtures (db_session, client, auth_headers)
├── unit/
│   ├── modules/<name>/test_service.py  ← one file per module service
│   └── shared/<name>/test_*.py         ← shared utilities
└── integration/
    └── modules/<name>/test_*_api.py    ← one file per module router
```

### Unit Tests (`tests/unit/`)

Required for **every** `application/service.py` method. Use `AsyncMock` for repositories — no real DB.

```python
from unittest.mock import AsyncMock
import pytest
from src.modules.deals.application.service import DealsService
from src.shared.exceptions.domain import NotFoundError

# --- Happy path ---
async def test_create_deal_returns_model():
    repo = AsyncMock()
    repo.create.return_value = deal_orm_fixture()
    service = DealsService(db=AsyncMock(), repo=repo)
    result = await service.create(payload_fixture(), owner_user_id=uuid.uuid4())
    assert result.stage == "new_lead"

# --- Error path: always test it ---
async def test_create_deal_raises_when_client_not_found():
    repo = AsyncMock()
    repo.get_client.return_value = None
    service = DealsService(db=AsyncMock(), repo=repo)
    with pytest.raises(NotFoundError):
        await service.create(payload_fixture(), owner_user_id=uuid.uuid4())
```

Rules:
- Test every branch: success, not-found, wrong owner, invalid state transition.
- Use `pytest.raises(DomainExceptionClass)` for every error path.
- Assert on `.message` when the error text matters to the contract.
- Group tests in a class per service method: `class TestCreate:`, `class TestTransitionStage:`.

### Integration Tests (`tests/integration/`)

Required for **every** API endpoint. Use real PostgreSQL (rolled back per test).

```python
from httpx import AsyncClient

class TestLoginEndpoint:
    async def test_success(self, client: AsyncClient, auth_headers: dict):
        resp = await client.post("/api/v1/auth/login", json={
            "email": "test@example.com", "password": "Test@1234!"
        })
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    async def test_wrong_password_returns_401(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/login", json={
            "email": "test@example.com", "password": "wrong"
        })
        assert resp.status_code == 401

    async def test_missing_field_returns_422(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/login", json={"email": "x@x.com"})
        assert resp.status_code == 422

    async def test_tenant_isolation(self, client: AsyncClient):
        # Create resource as user A, verify user B gets 404
        ...
```

**Minimum coverage per endpoint:**
- `200`/`201` success
- `401` unauthenticated
- `404` not found (where applicable)
- `422` schema validation failure
- Tenant isolation (user A cannot read user B's data)

Rules:
- Use `client` and `auth_headers` fixtures from `tests/conftest.py`.
- Never mock the database in integration tests.
- `auth_headers` fixture registers a real user via `POST /api/v1/auth/register` and returns `{"Authorization": "Bearer <token>"}`.

### Fixtures and Factories

Prefer **inline dict factories** over factory-boy. Factory-boy adds ORM coupling that fights the layered architecture.

```python
# In tests/conftest.py or a per-module conftest.py
import pytest_asyncio
from httpx import AsyncClient

@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient) -> dict:
    resp = await client.post("/api/v1/auth/register", json={
        "email": "test@example.com",
        "password": "Test@1234!",
        "full_name": "Test User",
    })
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

# Inline factory — simple, no ORM coupling
def make_deal_payload(**overrides) -> dict:
    return {"title": "Test Deal", "client_id": str(uuid.uuid4()), **overrides}
```

Rules:
- One `conftest.py` per test subdirectory for module-specific fixtures.
- Never share mutable state between tests.
- Async fixtures use `@pytest_asyncio.fixture`.

### AI Chain Tests (`tests/unit/ai/`)

Required for every `src/ai/<module>/chain.py`.

```python
VALID_RESPONSE = '{"score": 85, "recommendation": "qualify", "summary": "Strong lead"}'

def test_parse_output_valid():
    result = LeadQualifierChain()._parse_output(VALID_RESPONSE)
    assert result["score"] == 85
    assert result["recommendation"] == "qualify"

def test_parse_output_malformed_raises():
    with pytest.raises(AIOutputParseError):
        LeadQualifierChain()._parse_output("not valid json")

def test_prompt_template_renders():
    prompt = LeadQualifierChain()._build_prompt(deal_data={...}, client_data={...})
    assert len(prompt) > 0
```

Do NOT call the real OpenAI API in tests — use recorded response fixtures.

---

## Development Workflow

Implement in this order to minimize unresolved dependencies:

```
1. infrastructure/database  ← models, session, base mixins
2. alembic migrations       ← initial schema from schema.sql
3. shared/                  ← exceptions, pagination, events, dependencies
4. auth module              ← unblocks JWT on all other modules
5. users module             ← unblocks owner_user_id across all modules
6. subscriptions module     ← unblocks AI entitlement checks
7. clients module
8. deals module
9. proposals module         ← depends on deals
10. contracts module        ← depends on proposals
11. invoices module         ← depends on contracts + deals
12. reminders module        ← depends on all business objects
13. AI chains               ← lead_qualifier → proposal_generator → contract_generator → followup_generator
14. workers/                ← Celery tasks for AI, PDF, reminders
15. analytics module        ← reads from all operational tables
16. admin module            ← reads across everything
```

For each module, complete this checklist before moving on:

```
☐ domain/entities.py          + unit tests for invariant methods
☐ infrastructure/models.py    (PgEnum for all ENUM columns, create_type=False)
☐ infrastructure/repository.py + unit tests with AsyncMock db
☐ application/service.py      + unit tests (mocked repo, all branches)
☐ schemas/request.py + response.py
☐ api/router.py               + integration tests (success + all error paths)
☐ Alembic migration           (if schema changed)
```

---

## Common Mistakes to Avoid

### Architecture Violations

| Mistake | Correct Approach |
|---|---|
| Returning raw entity or list from a router | Wrap in `ApiResponse.ok(...)` or `PaginatedResponse.ok(...)`. |
| Returning ad-hoc dict `{"message": "ok"}` | Use `ApiResponse.ok(...)` with a typed response schema. |
| `raise HTTPException(...)` anywhere | Raise a domain exception — `setup_exception_handlers` converts it to `ApiError`. |
| Implementing a feature without tests | Unit-test every service method; integration-test every endpoint. Same task, not later. |
| Raising `HTTPException` inside a service | Raise domain exceptions (`NotFoundError`, `BusinessRuleError`). `shared/exceptions/http.py` translates them. |
| Putting `if/else` business logic in a router | Move to `application/service.py`. |
| Querying the DB directly from a router | Always go through service → repository. |
| Calling `langchain` from `src/modules/` | Use `AIFacade` only. |
| Importing one module's service into another | Communicate via domain events (`EventBus`) or a repository query. |
| Forgetting `WHERE deleted_at IS NULL` | Exposes soft-deleted records. |
| Forgetting `WHERE owner_user_id = :uid` | Leaks other users' data — critical security bug. |
| Using sync SQLAlchemy (`session.query()`) | Always `await session.execute(select(...))`. |
| ORM column typed as `String` for a PG ENUM | Use `PgEnum(..., create_type=False)` — asyncpg rejects implicit VARCHAR→ENUM cast. |
| Using `Optional[X]` | Use `X \| None` (Python 3.13). |
| Testing only the happy path | Always add: not-found, wrong owner, invalid state, 401, 422. |
| Mocking the DB in integration tests | Integration tests use real PostgreSQL (rolled back per test). |
| Writing business logic in `domain/entities.py` that calls I/O | Domain entities must be pure — no DB, no HTTP, no AI calls. |
| Modifying an append-only table | Always INSERT, never UPDATE on audit/log tables. |
| Applying AI-generated content directly to a live record | AI output is always draft. User must confirm before status advances. |
| Committing a migration that references a model not in `alembic/env.py` | Alembic won't detect the table. |

### Subscription / Entitlement

- Always check entitlement **before** consuming AI tokens — `AIFacade` does this automatically.
- A `suspended` subscription blocks AI features but not read access to existing data.
- Usage counters reset at `billing_period_start`, not on subscription creation.

### Deal Stage Transitions

- Valid stages: `new_lead` → `qualified` → `proposal_sent` → `in_negotiation` → `active` → `completed_and_billed`. Also `lost` (terminal, reachable from any non-terminal stage).
- Validate with `Deal.can_transition_to(target)` before any DB write.
- Transitioning to `active` requires at least one accepted Proposal linked to the Deal.
- Transitioning to `completed_and_billed` requires at least one Invoice linked to the Deal.
- Moving to `lost` or `completed_and_billed` sets `closed_at` and cancels all pending Reminders.

### Contracts

- `deal_id` and `proposal_id` are immutable once set — never allow updates to these fields.
- `client_snapshot` must be populated at creation time from the live client record — never updated afterward.
- Only one contract may be `active` or `pending_signatures` per deal (enforced by partial unique index).

### Invoices

- `total = subtotal + tax_amount` — validate this before allowing `sent` status.
- `amount_paid` can never exceed `total` — validate on every payment record insertion.
- An invoice must be linked to a `contract_id` or `deal_id` — reject standalone invoices.

---

## File Reference

| File | Purpose |
|---|---|
| `src/main.py` | FastAPI app, router registration, lifespan |
| `src/config/settings.py` | All environment variables via pydantic-settings |
| `src/infrastructure/database/base.py` | `Base`, `UUIDMixin`, `TimestampMixin`, `SoftDeleteMixin` |
| `src/infrastructure/database/session.py` | Async engine, `get_db_session()` |
| `src/infrastructure/redis/client.py` | Redis connection pool, `get_redis()` |
| `src/infrastructure/celery/app.py` | Celery app + beat schedule |
| `src/shared/exceptions/domain.py` | Domain exception hierarchy |
| `src/shared/exceptions/http.py` | FastAPI exception handlers (domain → HTTP status) |
| `src/shared/pagination/models.py` | `PaginationParams`, `Page[T]` |
| `src/shared/events/bus.py` | In-process `EventBus` singleton |
| `src/shared/dependencies/auth.py` | `CurrentUser`, `AdminUser`, `CurrentUserId` |
| `src/shared/dependencies/db.py` | `DBSession` annotated type |
| `src/shared/security/passwords.py` | `hash_password()`, `verify_password()` — Argon2id via pwdlib |
| `src/shared/responses/response.py` | `ApiResponse[T]`, `PaginatedResponse[T]`, `ErrorResponse` |
| `src/shared/responses/error.py` | `ApiError`, `ValidationErrorDetail`, `ErrorCode` enum |
| `src/shared/responses/pagination.py` | `PaginationMetadata` |
| `src/ai/facade.py` | `AIFacade` — only AI entry point for business modules |
| `src/ai/shared/base.py` | `BaseAIChain` with retry + logging |
| `alembic/env.py` | Async Alembic env — import models here |
| `tests/conftest.py` | Real DB fixtures, ASGI test client |
| `docs/database/schema.sql` | Full PostgreSQL schema reference |
| `contracts/openapi.yaml` | Full API contract (OpenAPI 3.1.0) |
| `Makefile` | All dev commands (`make up`, `make migrate`, `make test`, etc.) |
