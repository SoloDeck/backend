# ADR-004: Celery for Async Task Processing

**Status:** Accepted

---

## Context

Several SoloDesk operations cannot run synchronously in an HTTP request:
- AI generation (LLM calls can take 5–30 seconds)
- PDF rendering
- Email and Zalo message delivery
- Scheduled reminder dispatch
- Periodic jobs: overdue invoice detection, analytics snapshot refresh

These tasks need reliable execution, retry on failure, and scheduling (cron-like).

## Problem

How should the system execute long-running and scheduled background jobs?

## Decision

Use **Celery 5** with **Redis** as both broker and result backend.

- `CELERY_BROKER_URL` → `redis://redis:6379/1`
- `CELERY_RESULT_BACKEND` → `redis://redis:6379/2`
- Task definitions live in `src/workers/`: `ai_jobs/`, `pdf_jobs/`, `reminder_jobs/`, `scheduler/`.
- **Celery beat** runs as a separate container (`beat` Docker stage) for scheduled tasks.
- Beat schedule defined in `src/infrastructure/celery/app.py`:
  - `send_pending_reminders` — every 60 seconds
  - `mark_overdue_invoices` — every 3600 seconds
  - `refresh_analytics_snapshots` — every 86400 seconds
- Worker processes run as a separate container (`worker` Docker stage) with `--concurrency=4`.
- All AI tasks go through Celery — never triggered inline in HTTP handlers.

## Alternatives Considered

| Alternative | Reason Rejected |
|-------------|-----------------|
| FastAPI `BackgroundTasks` | No persistence, no retry, lost on process restart — insufficient for AI jobs |
| APScheduler | Good for scheduling but no distributed worker queue; no retry guarantees |
| RQ (Redis Queue) | Simpler but less mature scheduler; fewer monitoring options |
| Dramatiq | Good alternative but smaller ecosystem; less documentation for Python 3.13 |
| Cloud task queues (SQS, Cloud Tasks) | Vendor lock-in; over-engineered for current scale |

## Consequences

**Positive:**
- Proven reliability at scale; large ecosystem.
- Beat scheduler eliminates the need for OS cron.
- Redis already in the stack — no new infrastructure.
- Task retries with exponential backoff via Celery built-ins.
- Flower dashboard available for monitoring.

**Negative:**
- Celery workers and beat run as separate processes — adds Docker service count.
- Task serialization (pickle vs JSON) requires care with complex Python objects; use JSON-safe payloads only.
- Long-running AI tasks can starve short reminder tasks if concurrency is not tuned — use separate queues for AI vs reminders in production.
- Result backend in Redis is ephemeral — results expire; do not rely on them for business data (write results to DB instead).
