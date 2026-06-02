# SoloDesk Backend

SoloDesk is an **AI-powered CRM and deal management platform** built for Vietnamese
freelancers. It provides a complete end-to-end workflow: from capturing a new lead,
qualifying it with AI, generating a proposal, formalising a contract, issuing invoices,
and automating follow-up reminders — all through a single REST API.

The backend is a **Python / FastAPI modular monolith** backed by PostgreSQL, Redis, and
Celery, with LangChain + OpenAI powering the AI generation layer.

---

## Features

| Feature | Description |
|---|---|
| **Client Management** | Address book with contact info, communication logs, tags, and relationship status tracking |
| **Deal Pipeline** | Six-stage sales pipeline (New Lead → Qualified → Proposal Sent → In Negotiation → Active → Completed & Billed) with AI-assisted lead qualification |
| **Proposal Generation** | Versioned proposals with AI-drafted content, shareable client links, and accept/reject workflow |
| **Contract Generation** | Contracts sourced from accepted proposals, amendment versioning, dual-party signing, payment milestones |
| **Invoice Management** | Line-item invoices with tax, partial payment tracking, overdue detection, and shareable client links |
| **Reminder Automation** | Scheduled reminders targeting any business object (deal, client, invoice, contract) with recurrence and AI-suggested message drafts |
| **Analytics** | Revenue snapshots, pipeline distribution, win-rate calculations, top-client rankings, and AI usage metrics |
| **Subscription Management** | Free / Pro / Agency plan tiers with per-feature entitlement gates and usage counters |
| **Admin** | User management, subscription overrides, system templates, feature flags, AI cost monitoring, and immutable audit logs |

---

## Architecture

SoloDesk uses a **Modular Monolith** pattern. Each business domain is a self-contained
module under `src/modules/`. Modules communicate through domain events rather than direct
cross-module imports.

```
┌─────────────────────────────────────────────────────────────────────────┐
│  HTTP Clients (frontend, mobile, integrations)                          │
└────────────────────────────┬────────────────────────────────────────────┘
                             │  REST  /api/v1/*
┌────────────────────────────▼────────────────────────────────────────────┐
│  FastAPI Application  (src/main.py)                                     │
│                                                                         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐ │
│  │  auth    │ │  users   │ │  deals   │ │proposals │ │  contracts   │ │
│  ├──────────┤ ├──────────┤ ├──────────┤ ├──────────┤ ├──────────────┤ │
│  │ api      │ │ api      │ │ api      │ │ api      │ │ api          │ │
│  │ service  │ │ service  │ │ service  │ │ service  │ │ service      │ │
│  │ domain   │ │ domain   │ │ domain   │ │ domain   │ │ domain       │ │
│  │ repo     │ │ repo     │ │ repo     │ │ repo     │ │ repo         │ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────────┘ │
│                                                                         │
│  + clients  invoices  reminders  subscriptions  analytics  admin        │
│                                                                         │
│  ┌─────────────────────────────┐   ┌─────────────────────────────────┐ │
│  │  src/ai/  (AI subsystem)    │   │  src/workers/  (Celery tasks)   │ │
│  │  facade.py                  │   │  ai_jobs  pdf_jobs  reminders   │ │
│  │  lead_qualifier             │   │  beat scheduler (hourly/nightly)│ │
│  │  proposal_generator         │   └─────────────────────────────────┘ │
│  │  contract_generator         │                                        │
│  │  followup_generator         │                                        │
│  └─────────────────────────────┘                                        │
└─────────────────────────────────────────────────────────────────────────┘
         │                          │                    │
         ▼                          ▼                    ▼
  ┌─────────────┐           ┌──────────────┐    ┌──────────────┐
  │ PostgreSQL  │           │    Redis      │    │   OpenAI     │
  │  (primary   │           │  (cache +     │    │  (gpt-4o)    │
  │   store)    │           │   broker)     │    │              │
  └─────────────┘           └──────────────┘    └──────────────┘
```

### Module internal structure

Every module follows the same four-layer layout:

```
modules/<name>/
├── api/router.py            # HTTP boundary — no business logic
├── application/service.py  # All business rules
├── domain/entities.py       # Pure Python dataclasses
├── infrastructure/
│   ├── models.py            # SQLAlchemy ORM models
│   └── repository.py        # DB queries only
└── schemas/
    ├── request.py           # Pydantic inbound validation
    └── response.py          # Pydantic serialisation
```

### Core business flow

```
Client  ──→  Deal  ──→  Proposal  ──→  Contract  ──→  Invoice
                  ↓            ↓              ↓
           AI Qualifier  AI Generator   AI Generator
                  ↓
             Reminders  ──→  Workers (Celery)
                  ↓
             Analytics (read-only derived)
```

---

## Tech Stack

| Category | Technology | Version |
|---|---|---|
| Language | Python | 3.13 |
| Web framework | FastAPI | ≥ 0.115 |
| ASGI server | Uvicorn | ≥ 0.34 |
| ORM | SQLAlchemy (async) | ≥ 2.0 |
| Database | PostgreSQL | 16 |
| Migrations | Alembic | ≥ 1.14 |
| Async PG driver | asyncpg | ≥ 0.30 |
| Data validation | Pydantic v2 | ≥ 2.10 |
| Settings | pydantic-settings | ≥ 2.7 |
| Auth | python-jose + passlib[bcrypt] | — |
| Cache / broker | Redis | 7 |
| Task queue | Celery + beat | ≥ 5.4 |
| AI orchestration | LangChain | ≥ 0.3 |
| LLM provider | OpenAI (gpt-4o) | ≥ 1.59 |
| HTTP client | httpx | ≥ 0.28 |
| Logging | structlog | ≥ 25.1 |
| Linting | Ruff | ≥ 0.9 |
| Formatting | Black | ≥ 25.1 |
| Type checking | Mypy | ≥ 1.14 |
| Testing | pytest + pytest-asyncio | ≥ 8.3 |

---

## Getting Started

### Prerequisites

- Python 3.13
- Docker & Docker Compose v2
- `make` (standard on macOS/Linux)

### 1. Clone and enter the project

```bash
git clone <repo-url>
cd be-py
```

### 2. Set up environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in the required values:

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | `postgresql+asyncpg://user:pass@host:5432/db` |
| `JWT_SECRET_KEY` | Yes | Random 32+ char string |
| `OPENAI_API_KEY` | Yes (AI features) | OpenAI platform key |
| `GOOGLE_CLIENT_ID` | OAuth only | Google OAuth 2.0 client ID |
| `GOOGLE_CLIENT_SECRET` | OAuth only | Google OAuth 2.0 client secret |
| `STRIPE_SECRET_KEY` | Billing only | Stripe secret key |

All other variables have sensible defaults for local development.

### 3. Install Python dependencies (optional — Docker handles this too)

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
make install
```

---

## Running Locally

All services are orchestrated with Docker Compose. The stack includes:

| Service | Port | Description |
|---|---|---|
| `migrate` | — | One-shot: applies migrations + seeds data, then exits |
| `api` | 8000 | FastAPI application with hot-reload |
| `db` | 5432 | PostgreSQL 16 |
| `redis` | 6379 | Redis 7 |
| `worker` | — | Celery worker (4 concurrent) |
| `beat` | — | Celery beat scheduler |
| `mailpit` | 1025 / 8025 | Local SMTP + email UI |
| `pgadmin` | 5050 | PostgreSQL web UI |

### Full stack (recommended)

```bash
# Build images and start everything — migrations and seed run automatically
make up

# Tail logs
make logs

# Tail only the API
make logs-api

# Stop everything
make down
```

When you run `make up` (`docker compose up --build -d`), Docker Compose starts services
in dependency order:

1. `db` becomes healthy
2. `migrate` runs `alembic upgrade head` then seeds default data, then **exits 0**
3. `api` and `worker` start only after `migrate` completes successfully

This means tables and seed data are always present before the API accepts traffic.
The `migrate` service is idempotent — running it again skips already-applied migrations
and skips already-existing seed rows.

### DB-only init (useful when iterating on migrations)

Start only the database and pgAdmin, initialise the schema, then bring up the rest:

```bash
# 1. Start only DB and pgAdmin
docker compose up -d db pgadmin

# 2. Apply migrations and seed (idempotent)
make db-init

# 3. Start the rest of the stack
docker compose up -d
```

`make db-init` runs `python scripts/bootstrap.py` inside a short-lived container
connected to the running `db` service.

### Running without Docker

```bash
# Start only infrastructure
docker compose up -d db redis

# Apply migrations locally (requires DATABASE_URL in .env or environment)
make migrate

# Seed default data
make seed

# Run API locally with hot-reload
make dev

# Run Celery worker locally
make worker-dev
```

---

## Database Initialisation

> **Why pgAdmin may show no tables:** pgAdmin connects to PostgreSQL but cannot create
> tables itself. Tables are created by running Alembic migrations. If you start only
> `docker compose up -d db pgadmin`, the database is empty until you run migrations.

### What gets seeded

After `make db-init` or `make up`, the database contains:

| Table | Seeded rows |
|---|---|
| `subscription_plans` | Free, Pro, Agency |
| `users` | `admin@solodesk.dev` (development only) |

### Connecting pgAdmin to PostgreSQL

Open **http://localhost:5050** and log in:

| Field | Value |
|---|---|
| Email | `admin@solodesk.dev` |
| Password | `admin` |

Click **Add New Server** and fill in the **Connection** tab:

| Field | Value |
|---|---|
| Name | `SoloDesk Local` |
| Host name/address | `db` ← Docker service name, **not** `localhost` |
| Port | `5432` |
| Maintenance database | `solodesk` |
| Username | `solodesk` |
| Password | `solodesk` |

After connecting, tables are visible under:

```
Servers > SoloDesk Local > Databases > solodesk > Schemas > public > Tables
```

> **Host note:** pgAdmin runs inside Docker and reaches PostgreSQL via the internal
> Docker network using the service name `db`. External tools (TablePlus, DBeaver,
> local `psql`) connect via `localhost:5432`.

### Expected result after init

- `alembic_version` table exists with one row (`0001`)
- ~26 tables visible under `public > Tables`
- `subscription_plans` contains 3 rows: Free, Pro, Agency
- `users` contains 1 row (`admin@solodesk.dev`) when `APP_ENV=development`

### Reset (destructive — dev/CI only)

```bash
# Drop schema, re-migrate, re-seed
make reset-db
```

This refuses to run when `APP_ENV=production` or `APP_ENV=staging`.

---

## Migrations

SoloDesk uses [Alembic](https://alembic.sqlalchemy.org/) with an async PostgreSQL engine.

```bash
# Apply all pending migrations (local)
make migrate

# Apply migrations via Docker against the running db service
make migrate-docker

# Create a new auto-generated migration
make revision msg="add client tags table"

# Roll back one migration
make downgrade

# Open a direct psql session (Docker)
make db-shell
```

> **Important:** Before running `make revision`, ensure all new SQLAlchemy model files
> are imported in `alembic/env.py`. Alembic only detects tables whose models are loaded
> at migration time.

The full reference schema is at `docs/database/schema.sql`.

---

## Testing

Tests require a running PostgreSQL instance. By default they connect to
`postgresql+asyncpg://solodesk:solodesk@localhost:5432/solodesk_test`.
Override with the `TEST_DATABASE_URL` environment variable.

```bash
# Full test suite with coverage report
make test

# Unit tests only (no DB required)
make test-unit

# Integration tests only
make test-integration

# Stop on first failure
make test-fast

# Run a specific test file
pytest tests/unit/modules/deals/test_service.py -v

# Run a specific test by name
pytest -k "test_stage_transition" -v
```

Test coverage must stay above **80%**. The CI gate enforces this via `--cov-fail-under=80`.

### Test architecture

| Layer | Location | What it tests | DB |
|---|---|---|---|
| Unit | `tests/unit/` | Application service business rules (mocked repo) | No |
| Integration | `tests/integration/` | Full HTTP → service → DB round-trips | Yes (real) |
| AI prompt | `tests/unit/ai/` | Chain `_parse_output()` with recorded fixtures | No |

---

## Linting

```bash
# Lint with Ruff
make lint

# Format with Black + Ruff auto-fix
make fmt

# Type-check with Mypy
make typecheck

# Run all quality checks
make check
```

Configuration is in `pyproject.toml`:

- **Ruff** — `target-version = "py313"`, line length 100, rules: E, F, I, N, W, UP, B, SIM
- **Black** — line length 100, target Python 3.13
- **Mypy** — strict mode, pydantic and sqlalchemy plugins enabled

---

## Project Structure

```
be-py/
│
├── src/
│   ├── main.py                    # FastAPI app, router registration, lifespan
│   ├── config/
│   │   └── settings.py            # All env vars via pydantic-settings
│   │
│   ├── modules/                   # 11 business domains
│   │   ├── auth/                  # JWT, OAuth, refresh tokens, password reset
│   │   ├── users/                 # User profile, professional profile, preferences
│   │   ├── subscriptions/         # Plans, entitlements, usage counters, billing events
│   │   ├── clients/               # Client address book, comms log, tags
│   │   ├── deals/                 # Pipeline management, stage transitions
│   │   ├── proposals/             # Proposal versioning, AI drafts, client response
│   │   ├── contracts/             # Contract lifecycle, amendments, signing, milestones
│   │   ├── invoices/              # Invoicing, payment recording, overdue detection
│   │   ├── reminders/             # Scheduled notifications, recurrence, delivery
│   │   ├── analytics/             # Revenue snapshots, pipeline metrics, win rate
│   │   └── admin/                 # User mgmt, audit logs, templates, feature flags
│   │
│   ├── ai/                        # AI subsystem (see AI Components)
│   │   ├── facade.py              # Single entry point — used by all business modules
│   │   ├── shared/base.py         # BaseAIChain with retry, logging, error handling
│   │   ├── lead_qualifier/        # Lead scoring chain
│   │   ├── proposal_generator/    # Proposal draft chain
│   │   ├── contract_generator/    # Contract draft chain
│   │   └── followup_generator/    # Follow-up message chain
│   │
│   ├── workers/                   # Celery tasks (see Workers)
│   │   ├── ai_jobs/               # Async AI generation tasks
│   │   ├── pdf_jobs/              # PDF rendering and storage tasks
│   │   ├── reminder_jobs/         # Reminder delivery + beat jobs
│   │   └── scheduler/             # Beat schedule definitions
│   │
│   ├── integrations/              # External provider clients
│   │   ├── stripe/                # Stripe billing webhooks
│   │   ├── google_oauth/          # Google OAuth 2.0 client
│   │   └── openai_client/         # OpenAI SDK wrapper
│   │
│   ├── infrastructure/            # Technical plumbing
│   │   ├── database/              # SQLAlchemy engine, session, base models
│   │   ├── redis/                 # Redis connection pool
│   │   ├── celery/                # Celery app + beat schedule config
│   │   ├── storage/               # Object storage (S3-compatible)
│   │   └── email/                 # SMTP client
│   │
│   └── shared/                    # Cross-cutting utilities
│       ├── dependencies/          # FastAPI DI: auth (JWT), db (session)
│       ├── exceptions/            # Domain exception hierarchy + HTTP handlers
│       ├── pagination/            # PaginationParams, Page[T]
│       ├── events/                # In-process EventBus
│       └── logging/               # structlog configuration
│
├── tests/
│   ├── conftest.py                # Shared fixtures: real DB, ASGI client, rollback
│   ├── unit/                      # Service-layer unit tests (mocked repo)
│   └── integration/               # Full-stack integration tests (real DB)
│
├── alembic/
│   ├── env.py                     # Async Alembic environment
│   └── versions/                  # Auto-generated migration files
│
├── docs/
│   ├── architecture/ARCHITECTURE.md
│   ├── domains/                   # Per-domain specification (13 files)
│   └── database/                  # ERD and schema docs (4 files)
│
├── contracts/
│   └── openapi.yaml               # OpenAPI 3.1.0 specification (4 585 lines)
│
├── CLAUDE.md                      # Persistent context for AI coding agents
├── AGENTS.md                      # AI agent instructions
├── pyproject.toml                 # Dependencies, tool configuration
├── Dockerfile                     # Multi-stage: runtime / worker / beat
├── docker-compose.yml             # Full local development stack
├── Makefile                       # Dev, test, lint, migrate commands
└── .env.example                   # Environment variable reference
```

---

## AI Components

The AI subsystem lives entirely under `src/ai/` and is accessed exclusively through
`AIFacade`. **No business module imports LangChain directly.**

### Architecture

```
Business Service (e.g. DealsService)
        │
        ▼  dependency injection
   AIFacade  (src/ai/facade.py)
        │
        ├─ checks subscription entitlement before every call
        ├─ logs all generation attempts to ai_cost_records
        │
        ▼
  BaseAIChain  (src/ai/shared/base.py)
        │
        ├─ tenacity retry (up to 3 attempts, exponential backoff)
        ├─ structured error handling → AIGenerationError / AIOutputParseError
        │
        ▼
  LangChain Chain + OpenAI (gpt-4o)
```

### AI modules

| Module | Input | Output | Used by |
|---|---|---|---|
| `lead_qualifier` | Deal data, client data | Score (0–100), recommendation (`qualify`/`pass`), reasoning | Deals service |
| `proposal_generator` | Deal, client, user profile, optional template | Structured `ProposalDraft` content | Proposals service |
| `contract_generator` | Deal, accepted proposal, client, user profile | Structured `ContractDraft` content | Contracts service |
| `followup_generator` | Deal, client, communication history, reminder type | Follow-up message text | Reminders service |

### Key rules

- AI output is always returned as a **draft**. The user must explicitly confirm before the document can be sent.
- If generation fails (timeout, API error, parse error), a typed `AIGenerationError` is raised — no silent partial results.
- Entitlement is checked before any LLM token is consumed. Users on the Free plan receive `402 ENTITLEMENT_REQUIRED`.
- Prompt templates live in `src/ai/<module>/prompts/system.txt` and are version-controlled.

---

## Workers

Background jobs run on Celery with Redis as the broker. The beat scheduler handles
periodic jobs.

### Task inventory

| Task | Trigger | Description |
|---|---|---|
| `ai_jobs.qualify_lead_async` | On-demand | Async lead qualification (for non-interactive flows) |
| `ai_jobs.generate_proposal_async` | On-demand | Async proposal generation |
| `ai_jobs.generate_contract_async` | On-demand | Async contract generation |
| `pdf_jobs.render_proposal_pdf` | On-demand | Render proposal to PDF → upload to object storage |
| `pdf_jobs.render_contract_pdf` | On-demand | Render contract to PDF |
| `pdf_jobs.render_invoice_pdf` | On-demand | Render invoice to PDF |
| `reminder_jobs.send_reminder` | On-demand | Deliver a single reminder via configured channel |
| `reminder_jobs.send_pending_reminders` | **Every minute** | Scan pending reminders due for execution |
| `reminder_jobs.mark_overdue_invoices` | **Every hour** | Mark invoices past `due_date` as overdue |
| `reminder_jobs.refresh_analytics_snapshots` | **Nightly** | Rebuild revenue and pipeline snapshot tables |

### Running workers

```bash
# Docker (recommended)
make up

# Locally
make worker-dev   # Celery worker
make beat-dev     # Celery beat scheduler
```

Monitor tasks via Flower (not bundled by default — add to `docker-compose.yml` if needed):

```bash
celery -A src.infrastructure.celery.app.celery_app flower
```

---

## API Documentation

The full API contract is defined in **OpenAPI 3.1.0** at `contracts/openapi.yaml`
(4 585 lines, 79 paths, ~115 operations).

| Environment | URL |
|---|---|
| Local (debug mode) | http://localhost:8000/docs |
| Local (ReDoc) | http://localhost:8000/redoc |
| Raw spec | http://localhost:8000/openapi.json |
| File | `contracts/openapi.yaml` |

> Swagger UI and ReDoc are only served when `DEBUG=true`. In production, serve the
> static `openapi.yaml` through your API gateway or documentation platform.

### Domain coverage

| Tag | Endpoints |
|---|---|
| Auth | Login, refresh, logout, Google OAuth, password reset |
| Users | Profile, professional profile, preferences |
| Subscriptions | Plan catalog, upgrade/downgrade/cancel, usage |
| Clients | CRUD, communication logs, tags |
| Deals | CRUD, stage transitions, AI qualification, activity log |
| Proposals | CRUD, send, AI generate, public client view, accept/reject |
| Contracts | CRUD, send, sign, amend, terminate, AI generate, milestones, public client view |
| Invoices | CRUD, send, void, payment recording, public client view |
| Reminders | CRUD, cancel |
| Analytics | Dashboard, revenue, pipeline, win rate, top clients, AI usage |
| AI | Lead qualify, proposal generate, contract generate, follow-up generate |
| Admin | Users, subscriptions, plans, AI costs, audit log, templates, feature flags, platform metrics |
| Public | Shareable links for proposals, contracts, invoices (no auth) |

---

## Contributing

### Branch strategy

| Branch | Purpose |
|---|---|
| `main` | Production-ready code. Protected. Requires PR + review. |
| `develop` | Integration branch. All feature branches merge here first. |
| `feat/<name>` | New feature (e.g. `feat/invoice-pdf-export`) |
| `fix/<name>` | Bug fix (e.g. `fix/overdue-detection-timezone`) |
| `chore/<name>` | Non-functional change (e.g. `chore/update-dependencies`) |
| `docs/<name>` | Documentation only |

### Development workflow

```bash
git checkout develop
git pull origin develop
git checkout -b feat/your-feature

# ... make changes ...

make check          # lint + typecheck
make test           # full test suite

git add .
git commit -m "feat: describe what and why"
git push origin feat/your-feature
# Open a PR targeting develop
```

### Implementation order for new modules

When implementing a new module or extending an existing one, follow this order:

```
1. domain/entities.py       — pure Python, no dependencies
2. infrastructure/models.py — SQLAlchemy model
3. alembic migration        — make revision msg="..."
4. infrastructure/repository.py
5. application/service.py
6. schemas/request.py + response.py
7. api/router.py
8. tests/unit/
9. tests/integration/
```

### PR checklist

- [ ] Business logic is in `application/service.py`, not in the router or repository
- [ ] New tables are imported in `alembic/env.py`
- [ ] `make migrate` runs cleanly
- [ ] `make check` passes (no lint or type errors)
- [ ] `make test` passes with ≥ 80% coverage
- [ ] New AI chains have prompt tests with recorded fixtures
- [ ] No direct `langchain` / `openai` imports inside `src/modules/`
- [ ] All user-scoped queries filter by `owner_user_id`
- [ ] Soft-deletable table queries filter by `deleted_at IS NULL`

### Further reading

| Document | Location |
|---|---|
| AI agent coding instructions | `CLAUDE.md` |
| Architecture decisions | `docs/architecture/ARCHITECTURE.md` |
| Domain specifications | `docs/domains/*.md` |
| Database design | `docs/database/` |
| Full API contract | `contracts/openapi.yaml` |
