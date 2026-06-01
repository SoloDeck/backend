# Review Checklist

Use this checklist before submitting any PR or considering a feature complete.

---

## Response Envelope Compliance

- [ ] Every endpoint returns `ApiResponse[T]` (single resource) or `PaginatedResponse[T]` (collection)
- [ ] No router returns a raw ORM model, raw list, or ad-hoc dict
- [ ] All error responses use the `ApiError` envelope (enforced by `setup_exception_handlers`)
- [ ] Error `code` field uses a value from `ErrorCode` enum — no free-form strings
- [ ] `VALIDATION_FAILED` errors include a populated `details` array with `field` + `message` per violation
- [ ] No `HTTPException` raised anywhere — domain exceptions only
- [ ] Integration tests assert envelope shape: `resp.json()["success"]`, `resp.json()["data"]`, `resp.json()["error"]["code"]`

---

## Pagination Compliance

- [ ] All list endpoints return `PaginatedResponse[T]`
- [ ] Response includes `pagination.total`, `pagination.page`, `pagination.page_size`, `pagination.total_pages`
- [ ] Query params `page` and `page_size` are accepted and forwarded to the service
- [ ] Empty results return `data: []` with `pagination.total: 0`, not a 404

---

## OpenAPI Compliance

- [ ] Endpoint response type uses `$ref: '#/components/schemas/ApiResponseBase'` (or module-specific allOf)
- [ ] Error responses reference `$ref: '#/components/schemas/ApiError'`
- [ ] New reusable schemas added under `components/schemas/`
- [ ] No inline response object definitions — always use `$ref`

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
| Router returns raw entity, list, or ad-hoc dict | Response envelope violation |
| `HTTPException` raised anywhere in codebase | Architecture violation — use domain exceptions |
| Error `code` not from `ErrorCode` enum | Response standard violation |
| List endpoint missing `pagination` object | Pagination compliance failure |
| Missing `WHERE owner_user_id` filter | Multi-tenant data leak |
| Missing `WHERE deleted_at IS NULL` | Exposes soft-deleted records |
| `HTTPException` in service | Architecture violation |
| `from langchain` in `src/modules/` | Architecture violation |
| AI output applied directly to `sent` status | Business rule violation |
| Updated an append-only table | Data integrity violation |
| `deal_id` or `client_id` mutated after creation | Immutability violation |
| No unit test for new service method | Definition of Done not met |
| OpenAPI not updated | Definition of Done not met |
| Integration test doesn't assert envelope shape | Test quality failure |
