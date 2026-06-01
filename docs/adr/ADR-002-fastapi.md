# ADR-002: FastAPI as Web Framework

**Status:** Accepted

---

## Context

The SoloDesk backend is an API server consumed by a frontend (React/Next.js) and potentially mobile clients. The primary language is Python 3.13. The server handles both synchronous CRUD operations and long-running AI tasks (offloaded to Celery).

## Problem

Which Python web framework should serve the HTTP layer?

## Decision

Use **FastAPI** with fully async request handling.

- All route handlers are `async def`.
- Dependency injection is handled by FastAPI's `Depends()` system (DB sessions, current user, service instances).
- Request/response validation uses Pydantic v2 (FastAPI's native integration).
- The OpenAPI spec is contract-first: `contracts/openapi.yaml` is served directly via a custom `openapi()` override rather than auto-generated from routes.
- `lifespan` context manager handles startup/shutdown (DB engine dispose, Redis pool close).

## Alternatives Considered

| Alternative | Reason Rejected |
|-------------|-----------------|
| Django REST Framework | Synchronous by default; heavier ORM coupling; less natural for pure async SQLAlchemy |
| Flask + Flask-RESTful | No native async; no built-in validation; too much boilerplate for DI |
| Litestar | Excellent async framework but smaller ecosystem and fewer agent-readable examples |
| aiohttp | Too low-level; no built-in DI or validation layer |

## Consequences

**Positive:**
- First-class `async/await` support matches async SQLAlchemy perfectly.
- Pydantic v2 integration gives free request validation and serialization.
- Built-in OpenAPI generation (overridden in our case but available as fallback).
- Large ecosystem; most AI/agent tooling examples use FastAPI.

**Negative:**
- FastAPI's `Depends()` can become deeply nested and hard to trace for new developers.
- No built-in admin panel (handled by custom `admin` module).
- Background tasks via `BackgroundTasks` are not used — we use Celery instead (more reliable for AI jobs).
