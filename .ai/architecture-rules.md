# Architecture Rules

## Pattern: Modular Monolith

SoloDesk is a modular monolith. Code is organized by business domain, not by technical layer.

Every domain is a self-contained module under `src/modules/<name>/`. No shared service layer exists across modules.

```
src/
├── modules/          ← 11 business domains
├── ai/               ← AI chains (cross-cutting, never imported by modules directly)
├── workers/          ← Celery task definitions
├── integrations/     ← External provider adapters
├── infrastructure/   ← DB engine, Redis, Celery app setup
└── shared/           ← Pagination, exceptions, events, dependencies
```

## Dependency Direction

Dependencies must only flow inward:

```
api/router
    ↓
application/service
    ↓               ↓               ↓               ↓
domain/entities  infrastructure/  ai/facade       shared/events/
                 repository
```

### Strictly Forbidden

| Violation | Why |
|-----------|-----|
| `api/router → infrastructure/repository` | Skips business rules |
| `infrastructure/repository → application/service` | Reverse dependency |
| `domain/entities → SQLAlchemy` | Domain must be pure Python |
| `src/modules/* → langchain` | Must go through AIFacade |
| `application/service → HTTPException` | Domain exceptions only |
| `Module A service → Module B repository` | Cross-domain DB access violates boundaries |

## Domain Ownership

Each domain owns exactly one aggregate root and its child entities.

No domain may write to another domain's tables directly — use domain events or call the owning service.

| Domain | Aggregate Root | Terminal States |
|--------|---------------|-----------------|
| Users | User | deleted |
| Auth | Credential | — (stateless tokens) |
| Subscriptions | Subscription | cancelled |
| Clients | Client | archived, deleted |
| Deals | Deal | lost, completed_and_billed |
| Proposals | Proposal | accepted, rejected, expired |
| Contracts | Contract | completed, terminated |
| Invoices | Invoice | paid, cancelled |
| Reminders | Reminder | cancelled, completed |
| Analytics | — (read-only projections) | — |
| Admin | — (cross-domain read) | — |

## Module Internal Layers

```
api/router.py        ← HTTP parse/respond only. One service call per endpoint.
application/service.py ← All business rules. Raises domain exceptions.
domain/entities.py   ← Pure Python dataclasses. Zero I/O.
infrastructure/
  models.py          ← SQLAlchemy ORM. No if/else, no business logic.
  repository.py      ← Queries only. Always filter owner_user_id + deleted_at.
schemas/
  request.py         ← Pydantic v2 inbound validation.
  response.py        ← Pydantic v2 with model_config from_attributes=True.
```

## Cross-Module Communication

Prefer domain events over direct calls. When a service must trigger action in another domain:

1. Emit a domain event via `EventBus.publish(event_name, payload)`
2. The target domain subscribes via `EventBus.subscribe(event_name, handler)`
3. For synchronous reads (e.g., Auth reading a User), a direct service call is acceptable

Never share repository instances across modules.
