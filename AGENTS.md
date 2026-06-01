# SoloDesk Backend AI Agent Instructions

You are a senior software architect and backend engineer working on SoloDesk.

## Project Overview

SoloDesk is an AI-powered CRM and deal management platform for Vietnamese freelancers.

Main business domains:

* Authentication
* Users
* Subscriptions
* Clients
* Deals
* Contracts
* Proposals
* Reminders
* Analytics
* Admin
* AI Automation

The backend stack is:

* Python 3.13
* FastAPI
* PostgreSQL
* SQLAlchemy 2.x
* Alembic
* Redis
* Celery
* LangChain
* OpenAI
* Pydantic v2

---

## Architecture Style

Use Modular Monolith Architecture.

DO NOT organize code by technical layers at project root.

BAD:

controllers/
services/
repositories/

GOOD:

modules/
deals/
clients/
contracts/
reminders/

Each module owns its API, application, domain and infrastructure code.

---

## Module Structure

Each module must follow:

modules/<module_name>/
├── api/
├── application/
├── domain/
├── infrastructure/
├── schemas/
└── README.md

---

## Dependency Rules

Allowed:

API → Application
Application → Domain
Application → Infrastructure

Forbidden:

API → Repository
Repository → API
Module → Database directly

---

## Business Logic Rules

Business rules belong only in Application layer.

Repositories contain data access only.

No business logic in controllers.

No business logic in SQLAlchemy models.

---

## AI Rules

All AI-related functionality belongs under:

src/ai/

Never place LangChain logic inside business modules.

Business modules must call AI Facade.

Example:

DealService
↓
AIFacade
↓
LeadQualifier

---

## Testing Rules

Every Application Service requires:

* Unit tests
* Integration tests

AI chains require:

* Prompt tests
* Parser tests

---

## Coding Standards

* Use type hints everywhere.
* Use dependency injection.
* Use async SQLAlchemy.
* Use Pydantic v2.
* Follow Ruff linting rules.
* Follow Black formatting.

---

## Deliverables

When implementing any feature:

1. Domain entities
2. Schemas
3. Repository
4. Application service
5. API endpoint
6. Unit tests
7. README update

Generate production-grade code.
