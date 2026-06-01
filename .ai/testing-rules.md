# Testing Rules

## Test Structure

```
tests/
├── conftest.py              ← shared fixtures (DB, ASGI client, auth headers)
├── unit/
│   ├── modules/
│   │   ├── auth/
│   │   ├── deals/
│   │   └── ...              ← one directory per domain
│   └── ai/
│       ├── lead_qualifier/
│       └── ...
└── integration/
    ├── auth/
    ├── deals/
    └── ...
```

---

## Unit Test Requirements

Unit tests cover `application/service.py` methods.

**Rules:**
- No real database — mock the repository using `AsyncMock`.
- No real HTTP — do not use `AsyncClient` in unit tests.
- No real AI calls — mock `AIFacade`.
- Test every happy path, every error condition, every state transition.

```python
# CORRECT unit test
async def test_transition_to_lost_from_new_lead():
    repo = AsyncMock()
    repo.get_by_id.return_value = make_deal(stage="new_lead")
    service = DealsService(db=AsyncMock(), repo=repo)

    result = await service.transition_stage(deal_id, "lost", user_id)

    assert result.stage == "lost"
    assert result.closed_at is not None

async def test_transition_to_lost_from_terminal_raises():
    repo = AsyncMock()
    repo.get_by_id.return_value = make_deal(stage="completed_and_billed")
    service = DealsService(db=AsyncMock(), repo=repo)

    with pytest.raises(TerminalStateError):
        await service.transition_stage(deal_id, "lost", user_id)
```

**Minimum coverage per service:**
- Every public method has at least one test
- Terminal state transitions raise the correct exception
- Not-found cases raise `NotFoundError`
- Ownership checks raise `ForbiddenError` for wrong user

---

## Integration Test Requirements

Integration tests cover `api/router.py` endpoints.

**Rules:**
- Use real PostgreSQL (from `tests/conftest.py` fixtures).
- Session is rolled back after each test — no data bleeds between tests.
- Use `AsyncClient` against the full ASGI app.
- Test the full HTTP → service → DB round-trip.
- Do NOT mock the database.
- Do NOT mock domain services (only AI facade may be mocked in integration tests).

```python
# CORRECT integration test
async def test_create_deal_returns_201(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/v1/deals",
        json={"title": "New deal", "client_id": str(client_id), "value": "5000"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["stage"] == "new_lead"

async def test_create_deal_wrong_owner_returns_403(client: AsyncClient, other_auth_headers: dict):
    resp = await client.get(f"/api/v1/deals/{deal_id}", headers=other_auth_headers)
    assert resp.status_code == 403
```

**Required integration tests per endpoint:**
- Happy path (2xx)
- Auth missing → 401
- Wrong owner → 403 (for user-scoped resources)
- Not found → 404
- Validation error → 422
- Business rule violation → 409 or 400 (per contract)

---

## AI Chain Test Requirements

AI chain tests cover `src/ai/<module>/chain.py`.

**Rules:**
- Record real LLM responses as fixture strings — never call real OpenAI in tests.
- Test `_parse_output()` with recorded fixture strings.
- Test that malformed output raises `AIOutputParseError`.
- Test prompt template rendering with sample inputs.
- Tests live in `tests/unit/ai/<module>/`.

```python
# CORRECT AI test
FIXTURE_LEAD_QUAL_RESPONSE = """
{
  "score": 78,
  "recommendation": "qualified",
  "reasoning": "High budget, clear timeline, known pain point"
}
"""

async def test_parse_output_returns_dict():
    chain = LeadQualifierChain(llm=AsyncMock())
    result = chain._parse_output(FIXTURE_LEAD_QUAL_RESPONSE)
    assert result["score"] == 78
    assert result["recommendation"] == "qualified"

async def test_parse_output_malformed_raises():
    chain = LeadQualifierChain(llm=AsyncMock())
    with pytest.raises(AIOutputParseError):
        chain._parse_output("not valid json")
```

---

## Test Fixtures (conftest.py)

Available fixtures from `tests/conftest.py`:

| Fixture | Scope | Description |
|---------|-------|-------------|
| `db_session` | function | Real async DB session, auto-rollback |
| `client` | function | `AsyncClient` with DB override |
| `auth_headers` | function | JWT headers for a test freelancer |
| `admin_headers` | function | JWT headers for a test admin |

---

## Running Tests

```bash
make test                  # all tests
make test-unit             # unit only (fast, no DB)
make test-integration      # integration only (requires DB)
make test-fast             # unit + lint (no DB — for CI pre-push)
```

Minimum coverage threshold: **80%** (enforced in `pyproject.toml`).
