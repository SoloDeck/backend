# SoloDesk Backend — Claude Code Context

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
| AI orchestration | LangChain + OpenAI (gpt-4o) |
| Validation | Pydantic v2 |
| Settings | pydantic-settings |
| Logging | structlog |
| Testing | pytest + pytest-asyncio |

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
├── integrations/     # External providers (stripe, google_oauth, openai_client)
├── infrastructure/   # Database, Redis, Celery app setup
├── shared/           # Pagination, exceptions, events, dependencies, logging
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
**Responsibilities:** deal CRUD, pipeline stage transitions, activity log, AI qualification trigger.
**Boundaries:** does NOT own proposal documents, contract documents, invoices, or reminders.
**Depends on:** Clients (client_id immutable after creation).
**Key rule:** stage transitions are forward-only; `completed_and_billed` and `lost` are terminal. Validate using `Deal.can_transition_to()` in the service layer.

### `proposals`
**Responsibilities:** proposal versioning, lifecycle (draft → sent → accepted/rejected/expired), shareable client link, AI generation trigger.
**Boundaries:** does NOT advance deal stages directly — emits `proposals.proposal_accepted` event.
**Depends on:** Deals (deal_id immutable).
**Key rule:** only one proposal per deal may be `sent` at any time; creating a new revision supersedes the previous.

### `contracts`
**Responsibilities:** contract creation from accepted proposal, content editing (draft only), signing workflow, amendment versioning, payment milestones.
**Boundaries:** does NOT own invoice creation — emits milestone events for Invoices to consume.
**Depends on:** Proposals (proposal must be `accepted`), Deals, Clients.
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

### Routers (`api/router.py`)
- Parse and validate HTTP input only.
- Call one application service method per endpoint.
- Return HTTP responses — no domain logic.
- Use `CurrentUser`, `CurrentUserId`, `AdminUser` from `src/shared/dependencies/auth.py`.
- Use `DBSession` from `src/shared/dependencies/db.py`.

```python
# CORRECT
@router.post("/{deal_id}/stage-transition", response_model=DealResponse)
async def transition_stage(
    deal_id: uuid.UUID,
    body: StageTransitionRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> DealResponse:
    service = DealsService(db)
    deal = await service.transition_stage(deal_id, body.target_stage, user_id)
    return DealResponse.model_validate(deal)

# WRONG — business logic in router
@router.post("/{deal_id}/stage-transition")
async def transition_stage(...):
    if deal.stage == "lost":
        raise HTTPException(...)  # ← this belongs in the service
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
- `response.py` — set `model_config = {"from_attributes": True}` so ORM models map cleanly.
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

---

## Testing Rules

### Unit Tests (`tests/unit/`)
Required for every `application/service.py` method.
- Mock the repository (inject a fake or use `unittest.mock.AsyncMock`).
- Test business rules, state transition validation, error conditions.
- No database, no HTTP.

```python
async def test_transition_to_lost_from_new_lead():
    repo = AsyncMock()
    repo.get_by_id.return_value = deal_fixture(stage="new_lead")
    service = DealsService(db=AsyncMock(), repo=repo)
    result = await service.transition_stage(deal_id, "lost", user_id)
    assert result.stage == "lost"
```

### Integration Tests (`tests/integration/`)
Required for every API endpoint.
- Use `tests/conftest.py` fixtures: real PostgreSQL test DB, rolled-back per test.
- Use `AsyncClient` against the full ASGI app.
- Test the HTTP → service → DB round-trip.
- Do not mock the database.

```python
async def test_create_deal(client: AsyncClient, auth_headers):
    resp = await client.post("/api/v1/deals", json={...}, headers=auth_headers)
    assert resp.status_code == 201
    assert resp.json()["stage"] == "new_lead"
```

### AI Prompt Tests (`tests/unit/ai/`)
Required for every AI chain (`src/ai/<module>/chain.py`).
- Test `_parse_output()` with real LLM response fixtures (recorded strings).
- Test that malformed output raises `AIOutputParseError`.
- Test prompt template rendering with sample inputs.
- Do NOT call the real OpenAI API in tests — use recorded fixtures.

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

For each module, implement in this order:
```
domain/entities.py  →  infrastructure/models.py  →  infrastructure/repository.py
  →  application/service.py  →  schemas/  →  api/router.py
  →  tests/unit/  →  tests/integration/
```

---

## Common Mistakes to Avoid

### Architecture Violations

| Mistake | Correct Approach |
|---|---|
| Raising `HTTPException` inside a service | Raise domain exceptions (`NotFoundError`, `BusinessRuleError`). The HTTP handler in `shared/exceptions/http.py` translates them. |
| Putting `if/else` business logic in a router | Move to `application/service.py`. |
| Querying the DB directly from a router | Always go through the service → repository chain. |
| Calling `langchain` from `src/modules/` | Use `AIFacade` only. |
| Importing one module's service into another module's service | Communicate via domain events (`EventBus`) or query the DB through a repository. |
| Forgetting `WHERE deleted_at IS NULL` | Will expose soft-deleted records to users. |
| Forgetting `WHERE owner_user_id = :uid` | Will leak other users' data — critical security bug. |
| Using sync SQLAlchemy (`session.query()`) | Always use async (`await session.execute(select(...))`). |
| Writing business logic in `domain/entities.py` that calls I/O | Domain entities must be pure — no DB, no HTTP, no AI calls. |
| Modifying an append-only table (communication logs, activity entries, payment records) | These are immutable audit records. Always insert, never update. |
| Applying AI-generated content directly to a sent/active record | AI output is always a draft. User must explicitly confirm before status advances. |
| Hardcoding `owner_user_id` filters only in some query paths | Apply the tenant filter in the repository, not the service, so it can never be accidentally omitted. |
| Committing a migration that references a model not imported in `alembic/env.py` | Alembic won't detect the table. Import every model module in `alembic/env.py`. |

### Subscription / Entitlement

- Always check entitlement **before** consuming AI tokens — `AIFacade` does this automatically.
- A `suspended` subscription blocks AI features but not read access to existing data.
- Usage counters reset at `billing_period_start`, not on subscription creation.

### Deal Stage Transitions

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
| `src/shared/exceptions/http.py` | FastAPI exception handlers |
| `src/shared/pagination/models.py` | `PaginationParams`, `Page[T]` |
| `src/shared/events/bus.py` | In-process `EventBus` |
| `src/shared/dependencies/auth.py` | `CurrentUser`, `AdminUser`, `CurrentUserId` |
| `src/shared/dependencies/db.py` | `DBSession` annotated type |
| `src/ai/facade.py` | `AIFacade` — only AI entry point for business modules |
| `src/ai/shared/base.py` | `BaseAIChain` with retry + logging |
| `alembic/env.py` | Async Alembic env — import models here |
| `tests/conftest.py` | Real DB fixtures, ASGI test client |
| `docs/database/schema.sql` | Full PostgreSQL schema reference |
| `contracts/openapi.yaml` | Full API contract (OpenAPI 3.1.0) |
| `Makefile` | All dev commands (`make up`, `make migrate`, `make test`, etc.) |
