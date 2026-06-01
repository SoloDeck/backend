# Review Checklist

Use this checklist before submitting any PR or considering a feature complete.

---

## Domain Validation

- [ ] Domain entity correctly models the aggregate root and its invariants
- [ ] Value objects are immutable (`frozen=True`) where appropriate
- [ ] State transitions are validated using entity methods (e.g., `Deal.can_transition_to()`)
- [ ] Terminal states cannot transition further (raises `TerminalStateError`)
- [ ] Immutable fields (e.g., `deal_id`, `client_id`, `client_snapshot`) cannot be changed after creation
- [ ] `client_snapshot` is populated at creation time from the live record (for Contracts)
- [ ] Append-only tables are never updated (`deal_activity_entries`, `invoice_payment_records`, etc.)

---

## Architectural Validation

- [ ] No `HTTPException` raised inside a service — domain exceptions only
- [ ] No repository access from `api/router.py`
- [ ] No business `if/else` in `api/router.py`
- [ ] No LangChain or OpenAI imports in `src/modules/`
- [ ] AI access goes through `AIFacade` only
- [ ] Entitlement checked before any AI call (`subscription.can_use_ai`)
- [ ] Cross-module communication uses events or service calls — never cross-module repository access
- [ ] SQLAlchemy models contain no business logic

---

## API Validation

- [ ] Endpoint path matches `contracts/openapi.yaml`
- [ ] Request schema matches `contracts/openapi.yaml`
- [ ] Response schema matches `contracts/openapi.yaml`
- [ ] HTTP status codes match `contracts/openapi.yaml`
- [ ] Error responses use `ErrorResponse` schema
- [ ] Auth-required endpoints have no `security: []` override in the contract
- [ ] Public endpoints (share tokens) explicitly have `security: []`

---

## Database Validation

- [ ] New tables have `UUIDMixin` (UUID PK) and `TimestampMixin` (created_at/updated_at)
- [ ] Soft-deletable tables have `SoftDeleteMixin` (deleted_at)
- [ ] Append-only tables have `created_at` only (no `updated_at`)
- [ ] All user-scoped queries filter by `owner_user_id`
- [ ] All soft-deletable queries filter by `deleted_at IS NULL`
- [ ] New ORM models are imported in `alembic/env.py` for autogenerate
- [ ] Alembic migration created for every schema change
- [ ] `docs/database/schema.sql` updated to reflect schema changes

---

## Test Validation

- [ ] Unit test for every new service method
- [ ] Unit test for every error path in service methods
- [ ] Integration test for every new API endpoint (happy path)
- [ ] Integration test for 401 (unauthenticated), 403 (wrong owner), 404 (not found)
- [ ] AI chain tests cover `_parse_output()` with fixture strings
- [ ] No real OpenAI calls in any test
- [ ] Tests run with `make test` without errors
- [ ] Coverage threshold maintained (≥80%)

---

## Quick Rejection Criteria

Any of the following is an immediate rejection:

| Issue | Reason |
|-------|--------|
| Missing `WHERE owner_user_id` filter | Multi-tenant data leak |
| Missing `WHERE deleted_at IS NULL` | Exposes soft-deleted records |
| `HTTPException` in service | Architecture violation |
| `from langchain` in `src/modules/` | Architecture violation |
| AI output applied directly to `sent` status | Business rule violation |
| Updated an append-only table | Data integrity violation |
| `deal_id` or `client_id` mutated after creation | Immutability violation |
| No unit test for new service method | Definition of Done not met |
| OpenAPI not updated | Definition of Done not met |
