# Dependency Map

Full dependency diagram showing allowed and forbidden directions between all layers and modules.

---

## Layer Dependency Direction

```mermaid
graph LR
    subgraph "Module Internal Layers"
        direction TB
        ROUTER[api/router.py]
        SERVICE[application/service.py]
        DOMAIN[domain/entities.py]
        REPO[infrastructure/repository.py]
        MODELS[infrastructure/models.py]
    end

    subgraph "Cross-Cutting"
        SCHEMAS[schemas/request + response]
        SHARED_AUTH[shared/dependencies/auth.py]
        SHARED_DB[shared/dependencies/db.py]
        SHARED_EVENTS[shared/events/bus.py]
        SHARED_EXC[shared/exceptions/domain.py]
        AI_FACADE[ai/facade.py]
    end

    ROUTER -->|"calls"| SERVICE
    ROUTER -->|"uses"| SCHEMAS
    ROUTER -->|"uses"| SHARED_AUTH
    ROUTER -->|"uses"| SHARED_DB

    SERVICE -->|"calls"| REPO
    SERVICE -->|"raises"| SHARED_EXC
    SERVICE -->|"publishes"| SHARED_EVENTS
    SERVICE -->|"calls"| AI_FACADE
    SERVICE -->|"uses"| DOMAIN

    REPO -->|"queries"| MODELS
    MODELS -->|"extends"| BASE["database/base.py\n(UUIDMixin, TimestampMixin)"]
```

---

## Forbidden Dependencies

```mermaid
graph LR
    ROUTER -. "FORBIDDEN" .-> REPO
    REPO -. "FORBIDDEN" .-> SERVICE
    DOMAIN -. "FORBIDDEN" .-> MODELS
    SERVICE -. "FORBIDDEN" .-> HTTP_EXC["HTTPException"]
    MODULES -. "FORBIDDEN" .-> LANGCHAIN["langchain / openai"]
    MOD_A_SERVICE -. "FORBIDDEN" .-> MOD_B_REPO["another module's\nrepository"]
```

---

## Module Inter-Dependency Map

```mermaid
graph TD
    USERS[Users]
    AUTH[Auth]
    SUBS[Subscriptions]
    CLIENTS[Clients]
    DEALS[Deals]
    PROPOSALS[Proposals]
    CONTRACTS[Contracts]
    INVOICES[Invoices]
    REMINDERS[Reminders]
    ANALYTICS[Analytics]
    ADMIN[Admin]
    AI[AIFacade]

    USERS -->|"read user by email"| AUTH
    USERS -->|"user_created event"| SUBS
    USERS -->|"owner_user_id"| CLIENTS
    USERS -->|"owner_user_id"| DEALS

    SUBS -->|"can_use_ai entitlement"| AI

    CLIENTS -->|"client_id"| DEALS
    DEALS -->|"deal_id"| PROPOSALS
    PROPOSALS -->|"proposal_id"| CONTRACTS
    CONTRACTS -->|"contract_id"| INVOICES
    DEALS -->|"deal_id nullable"| INVOICES

    DEALS -->|"qualify_lead"| AI
    PROPOSALS -->|"generate_proposal"| AI
    CONTRACTS -->|"generate_contract"| AI
    DEALS -->|"generate_followup"| AI

    DEALS -->|"stage_transitioned event"| REMINDERS
    PROPOSALS -->|"proposal_sent event"| REMINDERS
    INVOICES -->|"invoice_overdue event"| REMINDERS
    CONTRACTS -->|"completed event"| REMINDERS

    PROPOSALS -->|"proposal_accepted event"| DEALS
    CONTRACTS -->|"milestone_reached event"| INVOICES
    INVOICES -->|"invoice_paid event"| DEALS

    DEALS -->|"read"| ANALYTICS
    INVOICES -->|"read"| ANALYTICS
    CLIENTS -->|"read"| ANALYTICS
    SUBS -->|"read"| ANALYTICS

    USERS -->|"read"| ADMIN
    SUBS -->|"read"| ADMIN
    DEALS -->|"read"| ADMIN
    INVOICES -->|"read"| ADMIN
```

---

## Dependency Rules Summary

| From | To | Type | Allowed? |
|------|----|------|----------|
| `api/router` | `application/service` | Direct call | ✅ |
| `api/router` | `infrastructure/repository` | Direct call | ❌ |
| `application/service` | `domain/entities` | Direct | ✅ |
| `application/service` | `infrastructure/repository` | DI injected | ✅ |
| `application/service` | `ai/facade` | DI injected | ✅ |
| `application/service` | `shared/events/bus` | Module-level singleton | ✅ |
| `application/service` | `HTTPException` | Import | ❌ |
| `infrastructure/repository` | `application/service` | Any | ❌ |
| `domain/entities` | SQLAlchemy | Import | ❌ |
| `src/modules/*` | `langchain` / `openai` | Import | ❌ |
| Module A service | Module B repository | Direct | ❌ |
| Module A service | Module B service | Direct call (read) | ⚠️ Auth→Users only |
| Module A service | Module B via event | EventBus | ✅ |
| `analytics` | Any domain table | Read-only query | ✅ |
| `admin` | Any domain service | Read-only call | ✅ |
