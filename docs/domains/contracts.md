# Contracts Domain

## Purpose

Generate, store, and manage formal service contracts between a freelancer and their clients. A Contract is the legally-oriented document that formalizes the terms of an engagement once a Proposal has been accepted. It provides a binding reference for the work to be delivered, the payment schedule, and the governing terms.

## Responsibilities

- Create a contract record from an accepted Proposal
- Store contract content: parties, scope, payment schedule, legal terms, IP clauses
- Version contracts when amendments are needed
- Track contract status (draft, active, completed, terminated)
- Generate a shareable/signable link for the client
- Record signing events (freelancer and client)
- Coordinate with AI domain to generate contract text from deal and proposal context
- Coordinate with Workers domain for PDF generation and storage

## Does Not Own

- Invoice creation or payment tracking (owned by **Invoices** domain)
- Proposal content or lifecycle (owned by **Proposals** domain)
- Client contact records (owned by **Clients** domain)
- Deal pipeline stage management (owned by **Deals** domain)
- Legal validity or e-signature infrastructure (out of scope; future integration)

## Core Concepts

**Contract** — The root aggregate. Has `contract_id` (UUID), `deal_id`, `proposal_id` (source proposal), `client_id`, `owner_user_id`, `version_number`, `status`, `content`, `signed_by_freelancer_at`, `signed_by_client_at`, `effective_date`, `end_date`.

**Contract Content** — A structured value object containing:
- `parties`: freelancer details (from User profile) and client details (from Client record)
- `scope_of_work`: the deliverables agreed upon (copied from accepted Proposal, may be refined)
- `payment_schedule`: list of payment milestones (description, amount, due_date)
- `payment_terms`: net terms (e.g. Net 15, Net 30), accepted payment methods
- `revision_policy`: number of included revisions, process for additional revisions
- `ip_ownership`: who owns deliverables and when ownership transfers
- `termination_clause`: conditions under which either party may terminate
- `governing_law`: jurisdiction (default: Vietnam; configurable)
- `custom_clauses`: freeform additional terms added by the freelancer

**Contract Status:**
- `draft` — Generated or being edited; not yet active
- `pending_signatures` — Sent to both parties for signing
- `active` — Both parties have signed; work is in progress
- `completed` — All deliverables delivered and final payment made
- `terminated` — Ended early by mutual agreement or breach
- `expired` — Signature deadline passed without completion

**Amendment** — A new contract version created when terms must change after the contract is `active`. The previous version is archived; the new version restarts the signing process.

**Payment Milestone** — A scheduled payment event within the contract: `description`, `amount`, `due_date`, `invoice_id` (linked once Invoice is issued). A contract must have at least one milestone.

## Business Rules

- A Contract must reference exactly one Deal and one source Proposal. Both `deal_id` and `proposal_id` are immutable once set.
- A Contract can only be created when the source Proposal has `status: accepted`.
- Creating a Contract automatically advances the parent Deal to stage `active`.
- Only one Contract may be in `active` or `pending_signatures` status per Deal at any time.
- A `draft` contract may be freely edited. Once moved to `pending_signatures`, content is locked except via Amendment.
- Both parties must sign for the contract to become `active`. Unilateral signing creates `pending_signatures` status.
- Contracts reference Client data (name, address) by value at creation time, not by live reference. This ensures contract immutability even if the client record is later updated.
- Payment milestones from the contract feed the Invoices domain: each milestone should correspond to a future Invoice.
- Terminated or expired contracts do not automatically close the Deal; the freelancer must decide the next action.

## Lifecycle

```
[proposals.proposal_accepted event received]
           │
           ▼
  [Contract Created: draft]
           │
   User reviews/edits content (or AI generates)
           │
           ▼
   [pending_signatures]
           │
      ┌────┴────┐
      ▼         ▼
[Freelancer  [Client
  signs]       signs]
      └────┬────┘
           ▼
       [active]
           │
   All milestones delivered and paid
           │
           ▼
      [completed]

   [active] ──── Amendment ────► [pending_signatures] (new version)
   [active/pending_signatures] ──► [terminated] (mutual or breach)
   [pending_signatures] ──► [expired] (deadline passed)
```

## Relationships

| Related Domain | Nature |
|---|---|
| **Proposals** | Contract is created from an accepted Proposal. Contract reads Proposal content as source material. |
| **Deals** | Contract belongs to one Deal. Contract activation advances Deal to `active`. |
| **Clients** | Contract embeds Client data by value at creation; holds a reference `client_id` for querying. |
| **Invoices** | Each payment milestone in a Contract may be linked to an Invoice. |
| **AI** | AI Contract Generator produces draft content from Proposal and Deal context. |
| **Workers** | PDF Workers render the Contract to PDF for storage and sharing. |
| **Reminders** | Reminders may target a Contract (e.g. "contract unsigned after 3 days"). |

## Events

| Event | Trigger | Consumers |
|---|---|---|
| `contracts.contract_created` | Contract draft saved | Analytics |
| `contracts.contract_sent_for_signing` | Moved to `pending_signatures` | Reminders (schedule signing nudge) |
| `contracts.freelancer_signed` | Freelancer signature recorded | Reminders (notify client to sign) |
| `contracts.client_signed` | Client signature recorded | Contract (check if both signed → activate) |
| `contracts.contract_activated` | Both parties signed | Deals (advance to `active`), Analytics, Reminders (schedule milestone reminders) |
| `contracts.contract_completed` | All milestones settled | Deals (advance to `completed_and_billed`), Analytics |
| `contracts.contract_terminated` | Termination event | Deals (notify freelancer), Reminders (cancel pending) |
| `contracts.amendment_created` | New version drafted | Previous version archived |

## Permissions

| Actor | Allowed Actions |
|---|---|
| **Authenticated User** | Create, edit (draft only), send, view own contracts; request AI generation; sign |
| **Client (via shareable link)** | View contract, submit signature — no authentication required |
| **Admin** | Read any contract for support; cannot modify |
| **Anonymous** | None (except via valid shareable link) |

## Future Considerations

- Legally-binding e-signature integration (qualified electronic signature per eIDAS or Vietnamese law)
- Contract clause library: reusable clause snippets for common situations
- Version diff view: highlight changes between contract amendments
- Automatic contract expiry warnings (e.g. 7 days before `end_date`)
- Multi-party contracts: deals involving more than one client signatory
- Contract compliance checks: AI review of clause legality per jurisdiction
