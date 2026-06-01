# Coding Rules

## Type Hints

Type hints are mandatory on every function and method — parameters and return types.

```python
# CORRECT
async def get_by_id(self, deal_id: uuid.UUID, owner_user_id: uuid.UUID) -> Deal | None:

# WRONG
async def get_by_id(self, deal_id, owner_user_id):
```

- `mypy --strict` must pass on all source files.
- Do not use `Any` unless wrapping an untyped third-party library (add a comment explaining why).
- Use `X | None` syntax (Python 3.10+ union), not `Optional[X]`.

## Async First

All service methods, repository methods, and route handlers must be `async def`.

```python
# CORRECT
async def create_deal(self, payload: CreateDealRequest, user_id: uuid.UUID) -> Deal:

# WRONG
def create_deal(self, payload: CreateDealRequest, user_id: uuid.UUID) -> Deal:
```

Never call synchronous SQLAlchemy (`session.query()`, `.filter()`, `.first()`) — always use `await session.execute(select(...))`.

Never use `time.sleep()` in async code — use `asyncio.sleep()`.

## Dependency Injection

Use FastAPI `Depends()` for all dependencies injected into route handlers.

```python
# CORRECT
@router.post("/deals")
async def create_deal(
    payload: CreateDealRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> DealResponse:
    return await DealsService(db=db).create_deal(payload, user_id)
```

Services receive `AsyncSession` in their constructor — never instantiate database connections directly inside a service.

AIFacade is injected into services as a parameter, never instantiated inside a router.

## Pydantic v2

All request and response models use Pydantic v2 `BaseModel`.

- Response models must have `model_config = {"from_attributes": True}` to map from ORM models.
- Use `Field(...)` with `min_length`, `max_length`, `ge`, `le` constraints on request fields.
- Never put business logic in Pydantic validators — validation is for data shape, not business rules.

```python
# CORRECT (shape validation in schema)
class CreateDealRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    value: Decimal = Field(..., ge=0)

# WRONG (business rule in schema)
class CreateDealRequest(BaseModel):
    @field_validator("value")
    def check_subscription(cls, v): ...  # ← belongs in service
```

## API Response Envelope

Every router must return the standard envelope. Raw entities, raw lists, and ad-hoc dicts are forbidden.

```python
from src.shared.responses import ApiResponse, PaginatedResponse

# CORRECT — single resource
@router.get("/{deal_id}", response_model=ApiResponse[DealResponse])
async def get_deal(...) -> ApiResponse[DealResponse]:
    deal = await DealsService(db=db).get(deal_id, user_id)
    return ApiResponse.ok(DealResponse.model_validate(deal))

# CORRECT — collection
@router.get("/", response_model=PaginatedResponse[DealResponse])
async def list_deals(...) -> PaginatedResponse[DealResponse]:
    items, total = await DealsService(db=db).list(user_id, page=page, page_size=page_size)
    return PaginatedResponse.ok(
        [DealResponse.model_validate(d) for d in items],
        total=total, page=page, page_size=page_size,
    )

# WRONG
return deal                    # raw ORM model
return items                   # raw list
return {"message": "created"}  # ad-hoc dict
raise HTTPException(...)       # use domain exceptions
```

Error responses are handled automatically by `setup_exception_handlers`. Raise domain exceptions
in services; they are converted to `ApiError` with the correct `ErrorCode`.

Required error codes (`src/shared/responses/error.py` → `ErrorCode`):

| Code | HTTP | When |
|---|---|---|
| `VALIDATION_FAILED` | 422 | Request schema invalid (auto-handled) |
| `UNAUTHORIZED` | 401 | Missing/invalid token |
| `FORBIDDEN` | 403 | Authenticated but not permitted |
| `NOT_FOUND` | 404 | Resource not found |
| `CONFLICT` | 409 | Duplicate or invalid state |
| `BUSINESS_RULE_VIOLATION` | 409 | Domain rule broken |
| `SUBSCRIPTION_REQUIRED` | 402 | Plan entitlement missing |
| `AI_QUOTA_EXCEEDED` | 502 | AI generation failed |
| `INTERNAL_SERVER_ERROR` | 500 | Unhandled exception |

## Error Handling

Services raise domain exceptions, never `HTTPException`:

| Situation | Exception |
|-----------|-----------|
| Record not found | `NotFoundError` |
| Duplicate record | `AlreadyExistsError` |
| Permission denied | `ForbiddenError` |
| AI entitlement blocked | `EntitlementError` |
| Invalid state transition | `InvalidStateTransitionError` |
| Immutable field change attempted | `ImmutableFieldError` |
| Already in terminal state | `TerminalStateError` |
| Generic business rule violation | `BusinessRuleError` |

All exceptions are translated to HTTP responses in `src/shared/exceptions/http.py`.

## Database Access

- Always use `async with session` / `await session.execute(select(...))`.
- Always filter soft-deleted records: `.where(Model.deleted_at.is_(None))`.
- Always filter by tenant: `.where(Model.owner_user_id == owner_user_id)`.
- Never call `.commit()` inside a repository — let the session context manage it.
- Never call sync SQLAlchemy methods.

## Comments

Write no comments by default.

Only add a comment when the WHY is non-obvious: a hidden constraint, a subtle invariant, a workaround for a specific bug.

Never write comments that describe WHAT the code does — well-named identifiers do that.

```python
# CORRECT — explains a non-obvious constraint
# stripe_subscription_id has a UNIQUE constraint but may be NULL for free-plan users
subscription.stripe_subscription_id = None

# WRONG — redundant
# Set the user's email
user.email = payload.email
```
