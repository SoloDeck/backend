# Clients Domain

## Purpose

Maintain a freelancer's address book of clients — the people and organizations they work with or pursue as prospects. This domain provides the client context that all deal, proposal, contract, and invoice records depend on.

## Responsibilities

- Create and store client records (individual and company)
- Manage client contact information (email, phone, social links, address)
- Record and retrieve communication history with each client
- Tag and categorize clients for filtering and segmentation
- Track client relationship status (prospect, active, inactive, archived)
- Provide client lookup and search for other domains
- Soft-delete client records

## Does Not Own

- Deal lifecycle and pipeline stages (owned by **Deals** domain)
- Proposal or contract documents (owned by **Proposals** and **Contracts** domains)
- Invoice generation or payment tracking (owned by **Invoices** domain)
- Automated follow-up scheduling (owned by **Reminders** domain)

## Core Concepts

**Client** — The root aggregate. Represents a contact or organization the freelancer works with. Has `client_id` (UUID), `owner_user_id`, `type` (`individual` | `company`), `name`, `email`, `phone`, `status`, and optional company-specific fields.

**Contact Info** — A value object storing `email`, `phone`, `website`, `linkedin_url`, `address` (city, country). Contact info belongs exclusively to one Client.

**Communication Log Entry** — An immutable record of a touchpoint with the client: `date`, `channel` (`email` | `phone` | `meeting` | `message`), `summary`, `created_by_user_id`. Append-only.

**Tag** — A short, user-defined label (e.g. `vip`, `long-term`, `retainer`) attached to a Client for filtering. Tags are user-scoped, not system-defined.

**Client Status** — The current relationship stage:
- `prospect` — Not yet a paying client; being evaluated
- `active` — Currently engaged in at least one open Deal
- `inactive` — Previously active but no open Deals
- `archived` — Manually archived; hidden from default views

## Business Rules

- A Client record is owned by exactly one User (`owner_user_id`). Users cannot access other users' clients.
- `email` must be unique within a single user's client list (two users may have the same client email independently).
- A Client with at least one open (non-completed) Deal automatically has `status: active`. This transition is triggered by the Deals domain via events.
- A Client cannot be hard-deleted if it has associated Deals, Contracts, or Invoices. Only soft-delete (archive) is permitted in that case.
- Communication Log Entries are append-only and cannot be modified or deleted.
- Tags are free-form text, stored lowercase. Maximum 10 tags per client.

## Lifecycle

```
[Client Created]
       │
       ▼
  [status: prospect]
       │
       ├─ Deal opened for client ────────────────► [status: active]
       │                                                  │
       │                              All deals closed/completed
       │                                                  │
       │                                         [status: inactive]
       │                                                  │
       │                              User archives client
       │                                                  │
       └──────────────────────────────────────────► [status: archived]
```

## Relationships

| Related Domain | Nature |
|---|---|
| **Users** | Each Client is owned by one User. Users domain provides the `owner_user_id`. |
| **Deals** | Each Deal references exactly one Client. A Client may have many Deals. |
| **Proposals** | Proposals reference Client for addressing and personalization. |
| **Contracts** | Contracts reference Client as the contracting party. |
| **Invoices** | Invoices are addressed to and tracked per Client. |
| **Reminders** | Reminders may target a specific Client (e.g. re-engagement reminders). |
| **AI** | AI Proposal and Follow-up generators consume Client data (name, company, history) as context. |

## Events

| Event | Trigger | Consumers |
|---|---|---|
| `clients.client_created` | New client record saved | Analytics (total client count) |
| `clients.client_updated` | Profile fields changed | AI (refresh generation context) |
| `clients.client_archived` | User archives client | Reminders (cancel future reminders for this client) |
| `clients.status_changed` | Status transitions (e.g. prospect → active) | Analytics |
| `clients.communication_logged` | New log entry added | Reminders (reset re-engagement timer) |

## Permissions

| Actor | Allowed Actions |
|---|---|
| **Authenticated User** | Full CRUD on own clients, log communication, manage tags |
| **Admin** | Read any client record for support purposes; cannot modify |
| **Anonymous** | None |

## Future Considerations

- Client portal: a read-only view shared with the client to track proposal/contract status
- Duplicate detection: warn when a new client email matches an existing record
- CRM import: bulk import from CSV, Google Contacts, or HubSpot
- Client scoring: AI-assisted rating based on deal size, payment history, and engagement
- Multi-contact support: associate multiple contacts (persons) under one company client
