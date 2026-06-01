# Domain Index

Complete domain map for the SoloDesk modular monolith.

---

## Domain Catalog

| # | Domain | Module Path | Status |
|---|--------|-------------|--------|
| 1 | Auth | `src/modules/auth/` | Scaffold |
| 2 | Users | `src/modules/users/` | Scaffold |
| 3 | Subscriptions | `src/modules/subscriptions/` | Scaffold |
| 4 | Clients | `src/modules/clients/` | Scaffold |
| 5 | Deals | `src/modules/deals/` | Scaffold |
| 6 | Proposals | `src/modules/proposals/` | Scaffold |
| 7 | Contracts | `src/modules/contracts/` | Scaffold |
| 8 | Invoices | `src/modules/invoices/` | Scaffold |
| 9 | Reminders | `src/modules/reminders/` | Scaffold |
| 10 | Analytics | `src/modules/analytics/` | Scaffold |
| 11 | Admin | `src/modules/admin/` | Scaffold |
| 12 | AI | `src/ai/` | Scaffold |

---

## Dependency Graph

Core business flow — every arrow is a hard dependency (aggregate must exist before dependent can be created):

```
Users ──────────────────────────────────────────────────────────┐
  └─► Subscriptions                                             │
  └─► Clients                                                   │
         └─► Deals ──────────────────────────────────────────► AI
                └─► Proposals                                   │
                       └─► Contracts                            │
                                └─► Invoices ◄──────────────────┘
                                       │
                                       ▼
                                  Reminders ◄── Deals
                                               ◄── Proposals
                                               ◄── Contracts
                                               ◄── Invoices

Analytics ◄── Deals, Invoices, Clients, Subscriptions (read-only)
Admin     ◄── All domains (read-only cross-domain)
```

Simplified linear view:

```
Client → Deal → Proposal → Contract → Invoice
Deal   → AI (lead qualification)
Proposal → AI (proposal generation)
Contract → AI (contract generation)
Deal → AI (follow-up generation)
Reminder → Deal | Proposal | Contract | Invoice
Analytics → Deal, Invoice, Client, Subscription
```

---

## Ownership Matrix

| Domain | Domain Owner | Aggregate Root | Data Owner | Notes |
|--------|-------------|----------------|------------|-------|
| Auth | Auth module | Credential | Auth | Does NOT own User profile |
| Users | Users module | User | Users | Leaf domain — no upstream deps |
| Subscriptions | Subscriptions module | Subscription | Subscriptions | One subscription per user |
| Clients | Clients module | Client | Clients | Scoped by `owner_user_id` |
| Deals | Deals module | Deal | Deals | Stage machine lives in domain entity |
| Proposals | Proposals module | Proposal | Proposals | Versioned per deal |
| Contracts | Contracts module | Contract | Contracts | Embeds client snapshot at creation |
| Invoices | Invoices module | Invoice | Invoices | Must link to deal or contract |
| Reminders | Reminders module | Reminder | Reminders | Polymorphic target, no DB FK |
| Analytics | Analytics module | — (read-only) | Source domains | Never writes operational tables |
| Admin | Admin module | — (read-only) | Source domains | Writes via other domain services |
| AI | AI module | — (stateless) | Calling service | Output always written by the caller |

---

## Cross-Domain Relationships

### Upstream → Downstream

```
Users
  ├── downstream: Auth (reads user by email)
  ├── downstream: Subscriptions (one per user)
  ├── downstream: Clients (owner_user_id)
  ├── downstream: Deals (owner_user_id)
  ├── downstream: Proposals (owner_user_id)
  ├── downstream: Contracts (owner_user_id)
  ├── downstream: Invoices (owner_user_id)
  ├── downstream: Reminders (owner_user_id)
  └── downstream: Analytics (scoped by owner_user_id)

Clients
  └── downstream: Deals (client_id — immutable after creation)
                    └── downstream: Proposals (deal_id — immutable)
                                      └── downstream: Contracts (proposal_id — immutable)
                                                        └── downstream: Invoices (contract_id nullable)

Subscriptions
  └── downstream: AI (entitlement check before any LLM call)

Deals
  └── downstream: Invoices (deal_id nullable)
  └── downstream: AI (qualify_lead, generate_followup)
  └── downstream: Reminders (target_type=deal)

Proposals
  └── downstream: AI (generate_proposal)
  └── downstream: Reminders (target_type=proposal)
  └── event: proposals.proposal_accepted → Deals (stage advance)

Contracts
  └── downstream: AI (generate_contract)
  └── downstream: Reminders (target_type=contract)
  └── event: contracts.milestone_reached → Invoices (create invoice)

Invoices
  └── downstream: Reminders (target_type=invoice)
```

### Communication Mechanisms

| From | To | Mechanism |
|------|----|-----------|
| Auth | Users | Direct service call (read user by email) |
| Proposals | Deals | Domain event `proposals.proposal_accepted` |
| Contracts | Invoices | Domain event `contracts.milestone_reached` |
| Any module | AI | Via `AIFacade` (DI injected into service) |
| Deals/Proposals/Contracts/Invoices | Reminders | Domain event or direct Reminder creation |
| Any closing transition | Reminders | Domain event auto-cancels pending reminders |

---

## Bounded Context Candidates

Future microservice extraction candidates, ordered by isolation readiness:

| Context | Domains Included | Extraction Readiness | Shared State Risk |
|---------|-----------------|---------------------|-------------------|
| **Identity** | Auth, Users | High — no upstream deps | JWT secret, user table |
| **Billing** | Subscriptions | High — thin Stripe adapter | User FK only |
| **CRM Core** | Clients, Deals | Medium — tightly coupled | Shared owner_user_id |
| **Document** | Proposals, Contracts | Medium — share deal/client refs | Proposal → Contract FK |
| **Finance** | Invoices | Medium — depends on Contracts | Contract FK |
| **AI Platform** | AI chains, Workers | High — stateless, pure output | Entitlement from Subscriptions |
| **Notifications** | Reminders | Medium — polymorphic targets | Polling / event sourcing needed |
| **Insights** | Analytics | High — read-only projections | Event-sourced snapshot |

> **Note:** No extraction should happen until each domain has a stable event log. All cross-context calls would become async over message bus.
