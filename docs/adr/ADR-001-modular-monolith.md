# ADR-001: Modular Monolith Architecture

**Status:** Accepted

---

## Context

SoloDesk is a greenfield product targeting Vietnamese freelancers. The team is small (1–3 engineers), the business requirements are still evolving, and the deployment target is a single VPS/container environment. A decision on top-level code organization was needed before the first line of business code was written.

## Problem

How should we organize the codebase to maximize development speed in the short term while preserving the ability to extract independent services in the future if the product scales?

## Decision

Adopt a **Modular Monolith** architecture.

- Code is organized by **business domain**, not by technical layer.
- Every domain is a self-contained module under `src/modules/<name>/`.
- Each module owns its API layer, application layer, domain layer, infrastructure layer, and schemas.
- Modules communicate via domain events (`EventBus`) or direct service calls — never by importing each other's repositories.
- There is a single deployable artifact. Worker processes (Celery) are separate OS processes but share the same codebase.

Directory shape:
```
src/
├── modules/         ← business domains
├── ai/              ← AI chains (cross-cutting, not a domain)
├── workers/         ← Celery task definitions
├── integrations/    ← external provider adapters
├── infrastructure/  ← DB, Redis, Celery app
└── shared/          ← utilities, pagination, exceptions, events
```

## Alternatives Considered

| Alternative | Reason Rejected |
|-------------|-----------------|
| Classic layered monolith (`controllers/services/repos/`) | Poor domain isolation; changes ripple across layers; harder to extract later |
| Microservices from day one | Operational overhead too high for a 1–3 person team; premature optimization |
| Hexagonal / Ports-and-Adapters | Valuable pattern but too much ceremony for current team size; can be adopted per-module incrementally |

## Consequences

**Positive:**
- Single deploy artifact — simple CI/CD.
- Domain boundaries are enforced by convention and code review, creating a natural migration path to microservices.
- Shared infrastructure (DB pool, Redis client) without network overhead.
- Easy to navigate — a developer can find all deal logic in `src/modules/deals/`.

**Negative:**
- Accidental coupling is possible (enforced only by convention, not the runtime).
- A single faulty migration or startup error affects all domains.
- Scaling individual domains requires extracting them first.
