# Definition of Done

A piece of work is **Done** only when every applicable checklist item below is satisfied.

---

## Feature DoD

A new domain feature (new endpoint, new service capability, new business rule):

- [ ] **Domain entity** — aggregate root or value object updated/added in `domain/entities.py`
- [ ] **SQLAlchemy model** — ORM model updated/added in `infrastructure/models.py`
- [ ] **Alembic migration** — migration generated and applied; model imported in `alembic/env.py`
- [ ] **Repository** — data access method added in `infrastructure/repository.py`
- [ ] **Service** — business logic implemented in `application/service.py`; all invariants enforced
- [ ] **Schemas** — Pydantic request/response models added in `schemas/`
- [ ] **Router** — endpoint added in `api/router.py`; no business logic in router
- [ ] **OpenAPI contract** — `contracts/openapi.yaml` updated with path + schema
- [ ] **Unit tests** — every new service method covered with mocked repository
- [ ] **Integration tests** — every new endpoint covered with real DB
- [ ] **schema.sql** — `docs/database/schema.sql` reflects new or changed tables
- [ ] **No architecture violations** — passes `.ai/review-checklist.md`
- [ ] **CI passes** — lint, typecheck, and tests all green

---

## API DoD

A new or changed API endpoint:

- [ ] Path, method, request body, response schema defined in `contracts/openapi.yaml`
- [ ] Response model uses `model_config = {"from_attributes": True}`
- [ ] All status codes defined (2xx, 401, 403, 404, 422 minimum)
- [ ] Auth requirement correct (`security: []` only for public endpoints)
- [ ] Integration test covers: happy path, wrong owner (403), not found (404), missing auth (401)
- [ ] Endpoint delegates to service — no business logic in router

---

## Database Change DoD

A schema migration (new table, new column, index change):

- [ ] Table/column added to `docs/database/schema.sql`
- [ ] SQLAlchemy model updated in `src/infrastructure/database/models.py`
- [ ] Alembic migration file generated (`make revision msg="..."`)
- [ ] Migration applied to local dev DB (`make migrate`)
- [ ] New model imported in `alembic/env.py`
- [ ] No previously-committed migration modified
- [ ] Multi-tenancy enforced: `owner_user_id` column present if user-scoped
- [ ] Soft-delete: `deleted_at` column present if record is soft-deletable
- [ ] Append-only constraint documented (no `updated_at` column) if applicable

---

## AI Feature DoD

A new AI-powered capability (lead qualification, generation, etc.):

- [ ] Chain implemented in `src/ai/<module>/chain.py` extending `BaseAIChain`
- [ ] System prompt stored in `src/ai/<module>/prompts/system.txt`
- [ ] `AIFacade` method added in `src/ai/facade.py`
- [ ] Entitlement check (`can_use_ai`) called before LLM invocation (inside `AIFacade`)
- [ ] AI cost logged to `ai_cost_records` on every call (success and failure)
- [ ] AI output always stored as `draft` — never applied directly to a `sent`/`active` record
- [ ] Chain unit tests: `_parse_output()` with fixture strings, malformed output raises `AIOutputParseError`
- [ ] No real OpenAI calls in any test
- [ ] Business module never imports LangChain or OpenAI directly

---

## Refactor DoD

An internal improvement that does not change observable behavior:

- [ ] No public API changes (request/response schema unchanged)
- [ ] No domain boundary changes (no concepts moved between modules)
- [ ] No OpenAPI contract changes required
- [ ] All existing tests pass without modification (behavior unchanged)
- [ ] Type safety maintained or improved
- [ ] No new architecture violations introduced
- [ ] If touching a module's internals: module's unit and integration tests still pass
