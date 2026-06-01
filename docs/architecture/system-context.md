# System Context

High-level view of SoloDesk and how its components interact with each other and with external systems.

---

## System Context Diagram

```mermaid
C4Context
    title SoloDesk — System Context

    Person(freelancer, "Vietnamese Freelancer", "Primary user — manages clients, deals, proposals, contracts, invoices")
    Person(client_person, "End Client", "Receives proposals, contracts, invoices via share links")
    Person(admin, "SoloDesk Admin", "Platform management, user oversight")

    System(solodesk, "SoloDesk Backend", "FastAPI modular monolith — CRM + AI automation")

    System_Ext(openai, "OpenAI API", "GPT-4o — lead qualification, proposal/contract/follow-up generation")
    System_Ext(stripe, "Stripe", "Subscription billing, webhooks")
    System_Ext(google, "Google OAuth", "Social login")
    System_Ext(smtp, "SMTP / Mailpit", "Email delivery (reminders, invoices, password reset)")
    System_Ext(storage, "Object Storage", "PDF and file storage (S3-compatible)")

    Rel(freelancer, solodesk, "Uses", "HTTPS / REST API")
    Rel(client_person, solodesk, "Views share links", "HTTPS — no auth required")
    Rel(admin, solodesk, "Manages platform", "HTTPS / Admin endpoints")

    Rel(solodesk, openai, "AI generation calls", "HTTPS")
    Rel(solodesk, stripe, "Subscription management", "HTTPS + webhooks")
    Rel(solodesk, google, "OAuth token exchange", "HTTPS")
    Rel(solodesk, smtp, "Sends emails", "SMTP")
    Rel(solodesk, storage, "Stores PDFs", "S3 API")
```

---

## Container Diagram

```mermaid
graph TB
    subgraph "Docker Compose / Production"

        subgraph "Client Layer"
            FRONTEND[Frontend\nReact / Next.js\n:3000]
            BROWSER[Browser\nShare link viewer]
        end

        subgraph "API Layer"
            API[FastAPI\nuvicorn :8000\n/api/v1/*]
        end

        subgraph "Worker Layer"
            WORKER[Celery Worker\n--concurrency=4\nai_jobs, pdf_jobs, reminder_jobs]
            BEAT[Celery Beat\nScheduler\nreminders, overdue, analytics]
        end

        subgraph "Data Layer"
            PG[(PostgreSQL 16\nPort 5432)]
            REDIS[(Redis 7\nPort 6379\nBroker + Cache)]
        end

        subgraph "Dev Tools"
            MAILPIT[Mailpit\nSMTP :1025\nUI :8025]
        end
    end

    FRONTEND -->|"REST API"| API
    BROWSER -->|"Share token endpoints"| API

    API -->|"async SQLAlchemy"| PG
    API -->|"asyncio-redis"| REDIS
    API -->|"enqueue tasks"| REDIS

    WORKER -->|"async SQLAlchemy"| PG
    WORKER -->|"dequeue + result"| REDIS
    WORKER -->|"SMTP"| MAILPIT

    BEAT -->|"schedule"| REDIS
```

---

## AI Interaction Flow

```mermaid
sequenceDiagram
    participant Router as api/router.py
    participant Service as application/service.py
    participant Facade as ai/facade.py
    participant Sub as SubscriptionsService
    participant Chain as LangChain Chain
    participant OpenAI as OpenAI API
    participant DB as PostgreSQL

    Router->>Service: qualify_lead(deal_id, user_id)
    Service->>DB: get deal + client
    Service->>Facade: qualify_lead(deal_data, client_data, can_use_ai)
    Facade->>Sub: check_entitlement(user_id, "can_use_ai")
    alt entitlement denied
        Facade-->>Service: raise EntitlementError
        Service-->>Router: 402 Payment Required
    end
    Facade->>Chain: chain.run(deal_data, client_data)
    Chain->>OpenAI: chat.completions.create(...)
    OpenAI-->>Chain: raw LLM response
    Chain-->>Facade: parsed dict {score, recommendation}
    Facade->>DB: INSERT ai_cost_records(...)
    Facade-->>Service: {score, recommendation}
    Service->>DB: UPDATE deal SET ai_score=..., ai_recommendation=...
    Service-->>Router: LeadQualificationResponse
```

---

## Worker Interaction Flow

```mermaid
sequenceDiagram
    participant Beat as Celery Beat
    participant Broker as Redis Broker
    participant Worker as Celery Worker
    participant DB as PostgreSQL
    participant SMTP as SMTP Server

    Beat->>Broker: enqueue send_pending_reminders (every 60s)
    Broker->>Worker: deliver task
    Worker->>DB: SELECT * FROM reminders WHERE scheduled_at <= NOW() AND status = 'pending'
    loop for each due reminder
        Worker->>SMTP: send email
        Worker->>DB: INSERT reminder_delivery_records(...)
        Worker->>DB: UPDATE reminders SET status = 'delivered'
    end

    Beat->>Broker: enqueue mark_overdue_invoices (every 3600s)
    Broker->>Worker: deliver task
    Worker->>DB: UPDATE invoices SET status = 'overdue' WHERE due_date < NOW() AND status = 'sent'
```

---

## Integration Boundaries

| External System | Direction | Adapter Location | Protocol |
|----------------|-----------|-----------------|---------|
| OpenAI | Outbound | `src/integrations/openai_client/` | HTTPS REST |
| Stripe | Inbound (webhooks) + Outbound | `src/integrations/stripe/` | HTTPS REST + webhook |
| Google OAuth | Outbound | `src/integrations/google_oauth/` | HTTPS OAuth 2.0 |
| SMTP | Outbound | `src/infrastructure/email/` | SMTP |
| Object Storage | Outbound | `src/infrastructure/storage/` | S3 API |
| Redis | Internal | `src/infrastructure/redis/client.py` | Redis protocol |
| PostgreSQL | Internal | `src/infrastructure/database/session.py` | asyncpg |

All external I/O goes through adapters in `src/integrations/` or `src/infrastructure/`. Business modules never import SDK clients directly.
