# Conceptual ERD — SoloDesk

## Overview

SoloDesk is a multi-tenant AI-powered CRM for Vietnamese freelancers. Every business entity is
owned by a **User** (the freelancer). All data is strictly isolated per user; no cross-user data
sharing exists at this tier.

---

## Domain Map

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  IDENTITY & ACCESS                                                          │
│                                                                             │
│   User ──────────────── OAuthIdentity                                       │
│     │                   RefreshToken                                         │
│     │                   PasswordResetToken                                   │
│     │                   TokenBlacklist                                        │
└─────┼───────────────────────────────────────────────────────────────────────┘
      │ owns
┌─────┼───────────────────────────────────────────────────────────────────────┐
│  BILLING                                                                    │
│                                                                             │
│   User ──── Subscription ──── SubscriptionPlan                              │
│     │            │                                                          │
│     │         UsageRecord                                                   │
│     │         BillingEvent                                                  │
└─────┼───────────────────────────────────────────────────────────────────────┘
      │ owns
┌─────┼───────────────────────────────────────────────────────────────────────┐
│  CRM CORE                                                                   │
│                                                                             │
│   User ──── Client ──── CommunicationLog                                    │
│     │          │         ClientTag                                          │
│     │          │                                                            │
│     │        Deal ──── DealActivityEntry                                    │
│     │          │                                                            │
│     │       Proposal ─────────────────────┐                                │
│     │          │                          │                                 │
│     │       Contract ──── PaymentMilestone│                                 │
│     │          │                          │                                 │
│     │       Invoice ──── LineItem         │                                 │
│     │          │         PaymentRecord    │                                 │
│     │          └──────────────────────────┘                                │
└─────┼───────────────────────────────────────────────────────────────────────┘
      │ owns
┌─────┼───────────────────────────────────────────────────────────────────────┐
│  ENGAGEMENT                                                                 │
│                                                                             │
│   User ──── Reminder ──── ReminderDeliveryRecord                            │
│               └── targets → Deal | Client | Invoice | Contract              │
└─────┼───────────────────────────────────────────────────────────────────────┘
      │ analytics for
┌─────┼───────────────────────────────────────────────────────────────────────┐
│  ANALYTICS (read-only derived)                                              │
│                                                                             │
│   User ──── RevenueSnapshot                                                 │
│     │        PipelineSnapshot                                               │
│     │        AICostRecord                                                   │
└─────┼───────────────────────────────────────────────────────────────────────┘
      │ administered by
┌─────┼───────────────────────────────────────────────────────────────────────┐
│  ADMIN                                                                      │
│                                                                             │
│   AuditLogEntry (platform-wide, actor = User)                               │
│   SystemTemplate                                                            │
│   FeatureFlag                                                               │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Aggregate Boundaries

| Aggregate Root | Owned Entities |
|---|---|
| **User** | Professional profile (embedded), Preferences (embedded) |
| **Subscription** | UsageRecord, BillingEvent |
| **Client** | CommunicationLog, ClientTag |
| **Deal** | DealActivityEntry |
| **Proposal** | ShareableLink (embedded token) |
| **Contract** | PaymentMilestone, ClientSnapshot (embedded value object) |
| **Invoice** | LineItem, PaymentRecord, ClientSnapshot (embedded value object) |
| **Reminder** | DeliveryRecord |
| **AuditLogEntry** | (immutable, no sub-entities) |
| **SystemTemplate** | (versioned via parent reference) |
| **AICostRecord** | (immutable log record) |

---

## Core Entity Relationships

### User is the Tenant Root

Every user-owned entity carries `owner_user_id`. A user in `deleted` status retains all records
(soft delete for compliance). A user in `suspended` status retains full data but receives HTTP 403
on all business operations.

### Client ← Deal

- A **Client** may have zero or many **Deals**.
- A **Deal** belongs to exactly one **Client** (immutable after creation).
- A Client's `status` is derived from the presence of open Deals (event-driven update).

### Deal → Proposal → Contract → Invoice

This is the primary document lifecycle chain:

```
Deal
 └── Proposal (1..N versions, one active at a time)
      └── Contract (created from an accepted Proposal)
           └── PaymentMilestone (1..N per Contract)
                └── Invoice (one per milestone; also directly linked to Deal)
```

- A **Deal** may have many **Proposal** versions but only one non-superseded sent/active version.
- A **Contract** is sourced from exactly one accepted **Proposal**; the deal and proposal refs are immutable.
- Only one Contract may be `active` or `pending_signatures` per Deal at any time.
- An **Invoice** must reference at least one of: `contract_id` or `deal_id`.

### Reminder → Any Target

**Reminder** is a polymorphic entity. It targets one business object via (`target_type`, `target_id`).
Target types: `deal`, `client`, `invoice`, `contract`.

### Subscription → Plan

- Each **User** has exactly one **Subscription** (1:1).
- Each **Subscription** references one **SubscriptionPlan**.
- **SubscriptionPlan** is a system catalog (not user-owned).

---

## Cardinality Summary

| From | Relationship | To |
|---|---|---|
| User | 1 : 0..1 | Subscription |
| User | 1 : 0..N | OAuthIdentity |
| User | 1 : 0..N | RefreshToken |
| User | 1 : 0..N | Client |
| User | 1 : 0..N | Deal |
| User | 1 : 0..N | Proposal |
| User | 1 : 0..N | Contract |
| User | 1 : 0..N | Invoice |
| User | 1 : 0..N | Reminder |
| User | 1 : 0..N | AICostRecord |
| User | 1 : 0..N | RevenueSnapshot |
| User | 1 : 0..N | PipelineSnapshot |
| SubscriptionPlan | 1 : 0..N | Subscription |
| Subscription | 1 : 0..N | UsageRecord |
| Subscription | 1 : 0..N | BillingEvent |
| Client | 1 : 0..N | Deal |
| Client | 1 : 0..N | CommunicationLog |
| Client | 1 : 0..10 | ClientTag |
| Deal | 1 : 0..N | Proposal |
| Deal | 1 : 0..N | DealActivityEntry |
| Deal | 1 : 0..N | Contract |
| Deal | 1 : 0..N | Invoice |
| Proposal | 1 : 0..1 | Contract |
| Contract | 1 : 1..N | PaymentMilestone |
| Contract | 1 : 0..N | Invoice |
| Invoice | 1 : 1..N | LineItem |
| Invoice | 1 : 0..N | PaymentRecord |
| Reminder | 1 : 0..N | DeliveryRecord |
| Reminder | 0..1 : 0..N | Reminder (parent for recurring series) |

---

## Key Business Invariants

1. **Multi-tenancy isolation** — every user-owned entity is filtered by `owner_user_id`. No row-sharing.
2. **Client email uniqueness** is scoped per owner user, not globally.
3. **Invoice requires business context** — must have `deal_id` or `contract_id` (or both).
4. **Deal stage transitions are forward-only** — `lost` and `completed_and_billed` are terminal.
5. **Contracts embed client data by value** (snapshot at creation) — immutable even if the Client record changes.
6. **Invoices embed client data by value** — same immutability guarantee.
7. **Append-only records** — CommunicationLog, DealActivityEntry, PaymentRecord, DeliveryRecord, AuditLogEntry are never updated or deleted.
8. **Soft delete** applies to: User, Client, Deal. Hard delete is never permitted when foreign records exist.
9. **Invoice numbers are user-scoped sequential** — never reused, even when voided.
10. **One active subscription per user** — the `subscriptions` table has a unique index on `user_id`.
