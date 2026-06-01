# SoloDesk Domain Documentation — Summary

This document provides the cross-cutting view of all SoloDesk domains: how they depend on each other, where the key relationships are, which aggregates exist, and how the system maps to bounded contexts.

---

## Domain Dependency Map

Arrows indicate "depends on" (reads data from or calls service of).

```
                        ┌─────────┐
                        │  Auth   │◄──────────────────────────────┐
                        └────┬────┘                               │
                             │ issues JWT with subscription_tier  │ revoke sessions
                             ▼                                    │
                        ┌─────────┐                         ┌──────────┐
                        │  Users  │◄────────────────────────│  Admin   │
                        └────┬────┘  manage users           └────┬─────┘
                             │                                   │ reads all
                             │ owned by user                     │
              ┌──────────────┼──────────────┐                    │
              ▼              ▼              ▼                    │
         ┌─────────┐   ┌─────────┐   ┌──────────────┐           │
         │ Clients │   │  Deals  │   │Subscriptions │◄──────────┘
         └────┬────┘   └────┬────┘   └──────┬───────┘
              │             │               │ entitlement check
              │             │               ▼
              │       ┌─────┴──────┐   ┌─────────┐
              │       │            │   │   AI    │
              │       ▼            ▼   └────┬────┘
              │  ┌──────────┐ ┌──────────┐  │ outputs drafts
              │  │Proposals │ │Contracts │◄─┘
              │  └────┬─────┘ └────┬─────┘
              │       │            │
              │       └─────┬──────┘
              │             ▼
              │        ┌──────────┐
              └───────►│ Invoices │
                        └────┬─────┘
                             │
              ┌──────────────┼──────────────────┐
              ▼              ▼                  ▼
        ┌──────────┐   ┌───────────┐     ┌───────────┐
        │Reminders │   │ Analytics │     │  Workers  │
        └──────────┘   └───────────┘     └───────────┘
```

**Legend:**
- Solid dependencies: synchronous service calls or read queries
- Analytics and Admin: read from all domains (not shown to avoid clutter)
- Workers: execute jobs dispatched by Reminders, AI, and PDF generation tasks

---

## Cross-Domain Relationships

| Relationship | Type | Description |
|---|---|---|
| Auth → Users | Read | Auth reads User credentials and profile to issue JWT |
| Auth → Subscriptions | Read | Auth embeds `subscription_tier` in token at login |
| Users → (all domains) | Reference | All domains store `owner_user_id` referencing a User |
| Clients → Deals | One-to-many | One Client may have many Deals |
| Deals → Proposals | One-to-many | One Deal may have multiple Proposal versions |
| Deals → Contracts | One-to-one (active) | One active Contract per Deal |
| Deals → Invoices | One-to-many | A Deal may have multiple milestone Invoices |
| Proposals → Contracts | One-to-one | A Contract is created from an accepted Proposal |
| Contracts → Invoices | One-to-many | Contract milestones correspond to Invoices |
| Subscriptions → AI | Entitlement gate | AI checks subscription entitlement before every generation |
| AI → Proposals | Output | AI Proposal Generator produces draft content for Proposals |
| AI → Contracts | Output | AI Contract Generator produces draft content for Contracts |
| AI → Reminders | Output | AI Follow-up Generator produces message text for Reminders |
| Deals → Analytics | Read (derived) | Analytics reads Deal stages and values for pipeline metrics |
| Invoices → Analytics | Read (derived) | Analytics reads Invoice payments for revenue metrics |
| Reminders → Workers | Dispatch | Reminders creates Celery jobs in Workers for delivery |
| Admin → (all domains) | Read-only oversight | Admin reads any domain for support and audit purposes |

---

## Aggregate Candidates

An aggregate is a cluster of domain objects treated as a single unit for consistency. Each aggregate has one root entity that controls access.

| Aggregate Root | Owned Value Objects / Entities | Notes |
|---|---|---|
| **User** | `ProfessionalProfile`, `Preferences` | Owns identity and personal configuration |
| **Subscription** | `UsageRecord`, `BillingEvent[]` | One per User; enforces entitlement invariants |
| **Client** | `ContactInfo`, `Tag[]`, `CommunicationLog[]` | Communication log is append-only child collection |
| **Deal** | `ActivityEntry[]` | Owns pipeline stage transition rules |
| **Proposal** | `ProposalContent`, `LineItem[]` | Each version is a separate aggregate instance |
| **Contract** | `ContractContent`, `PaymentMilestone[]`, `Amendment[]` | Immutable once signed; amendments create new versions |
| **Invoice** | `LineItem[]`, `PaymentRecord[]` | Payment records append-only; totals must balance |
| **Reminder** | `RecurrenceRule`, `DeliveryRecord[]` | Delivery records are append-only |
| **GenerationRequest** | `GenerationResult` | AI domain; request + result form one consistent unit |
| **SystemTemplate** (Admin) | `TemplateContent` | Versioned; Admin root aggregate |
| **AuditLogEntry** (Admin) | _(none; fully atomic)_ | Immutable, no child objects |

---

## Suggested Bounded Contexts

A bounded context groups domains that share a ubiquitous language and can be developed and deployed as a coherent unit. For SoloDesk's modular monolith, these are logical boundaries — not separate services — but they identify natural seams for future extraction.

### 1. Identity Context
**Domains:** Auth, Users

**Rationale:** Both domains speak the same language around "who is this person and how did they get in." Auth depends directly on Users and neither is useful without the other. Token issuance and profile management are tightly coupled.

**Key language:** User, credential, session, token, role, profile

---

### 2. Sales Pipeline Context
**Domains:** Clients, Deals

**Rationale:** These two domains form the core CRM loop. A Deal has no meaning without a Client. Both domains are actively managed during prospecting and are read together in every pipeline view. The freelancer's daily workflow is primarily in this context.

**Key language:** Client, deal, pipeline, stage, lead, opportunity, prospect

---

### 3. Engagement Documents Context
**Domains:** Proposals, Contracts

**Rationale:** Proposals and Contracts are the formal documents that move a deal from qualified to contracted work. They share a close lifecycle dependency (contract from accepted proposal) and the same conceptual vocabulary (scope, terms, parties, signatures).

**Key language:** Proposal, contract, scope of work, terms, revision, signature, effective date

---

### 4. Billing Context
**Domains:** Invoices

**Rationale:** Invoices are the financial record domain. They consume data from Contracts and Deals but speak a distinct financial language (line items, taxes, payment records, overdue, void). As the product grows (payment gateways, accounting integrations), this context will need to evolve independently.

**Key language:** Invoice, payment, line item, due date, overdue, void, revenue

---

### 5. Platform Operations Context
**Domains:** Subscriptions, Admin

**Rationale:** These domains govern the platform itself rather than the freelancer's client work. Subscriptions controls what users can do; Admin controls the platform. Both are operated by a different persona (SoloDesk operator vs. freelancer) and share platform-level language.

**Key language:** Plan, entitlement, tier, usage limit, audit log, feature flag, template

---

### 6. Intelligence Context
**Domains:** AI, Reminders

**Rationale:** Both domains augment the freelancer's workflow without owning business state. AI generates content; Reminders schedule nudges. Both are triggered by business events in other contexts and return structured outputs back. They share a dependency on Workers for async execution and on Subscriptions for entitlement.

**Key language:** Generation, draft, qualification, follow-up, reminder, schedule, channel

---

### 7. Insights Context
**Domains:** Analytics

**Rationale:** Analytics is a standalone read model. It consumes events from every other context and serves a dedicated dashboard query API. It has no write path into any business domain. As data volumes grow, this context is the most natural candidate for extraction into a separate read store (e.g. TimescaleDB, ClickHouse).

**Key language:** Revenue, win rate, pipeline value, conversion rate, metric, snapshot, period

---

## Notes on Cross-Context Communication

Within the modular monolith, cross-context calls are direct in-process service calls. The boundaries above define which modules should be treated as "external" to each other:

- **Prefer events over direct calls** across context boundaries where eventual consistency is acceptable (e.g. Analytics consuming Deal events).
- **Use direct service calls** where strong consistency is required (e.g. AI checking Subscription entitlement synchronously before consuming tokens).
- **AIFacade** is the mandatory anti-corruption layer between the Sales Pipeline / Engagement Documents contexts and the Intelligence context. Business modules must never import LangChain directly.
- If SoloDesk later splits into microservices, each bounded context above maps to one candidate service — the event contracts defined in each domain document become the inter-service API.
