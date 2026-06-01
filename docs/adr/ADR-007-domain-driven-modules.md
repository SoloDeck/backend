# ADR-007: Domain-Driven Module Structure

**Status:** Accepted

---

## Context

Within the modular monolith (see ADR-001), each domain module needs a consistent internal layout. Without a standard, developers would organize code differently per module, making the codebase harder to navigate and easier to violate layering rules.

## Problem

What internal structure should each domain module follow, and what are the strict layering rules between layers?

## Decision

Every domain module follows a **four-layer internal structure**:

```
modules/<name>/
├── api/
│   └── router.py          ← HTTP boundary only
├── application/
│   └── service.py         ← All business rules
├── domain/
│   └── entities.py        ← Pure Python, zero I/O
├── infrastructure/
│   ├── models.py          ← SQLAlchemy ORM
│   └── repository.py      ← DB queries only
└── schemas/
    ├── request.py          ← Pydantic v2 inbound
    └── response.py         ← Pydantic v2 outbound
```

**Allowed dependency directions:**
```
api/router  →  application/service  →  domain/entities
                                    →  infrastructure/repository
                                    →  ai/facade (via DI)
                                    →  shared/events/bus
```

**Forbidden cross-layer calls:**

| From | To | Reason |
|------|----|--------|
| `api/router` | `infrastructure/repository` | Skips business rules |
| `infrastructure/repository` | `application/service` | Reverse dependency |
| `domain/entities` | SQLAlchemy / DB | Domain must be pure |
| `application/service` | `HTTPException` | Domain exceptions only |
| Any module | `langchain` / `openai` directly | Must use AIFacade |
| One module's service | Another module's repository | Cross-domain DB access via events or shared queries |

## Alternatives Considered

| Alternative | Reason Rejected |
|-------------|-----------------|
| Flat module structure (no layers) | No enforcement boundary; business logic and DB queries mix |
| Hexagonal per module | Too much abstraction (ports/adapters) for current team size |
| Shared service layer across modules | Tight coupling; defeats modular isolation |
| CQRS within each module | Valuable but premature — add when read/write models diverge significantly |

## Consequences

**Positive:**
- New developers (or AI agents) know exactly where to find any type of code.
- Layer violations are immediately visible in code review and import analysis.
- Domain entities are pure Python — unit-testable without a database.
- Repositories are mockable — service tests don't need a DB connection.

**Negative:**
- More files per feature than a flat structure (5–6 files minimum for a new endpoint).
- Thin modules (e.g., Analytics, which is read-only) have boilerplate layers that add little value.
- The boundary between "business rule in service" vs "query optimization in repository" requires judgment — documented in CLAUDE.md examples.
