# Proposals Domain

## Purpose

Manage the creation, versioning, and delivery of formal business proposals sent from a freelancer to a client. A Proposal is the document that defines scope, timeline, and pricing for a potential engagement — it lives within the context of a Deal and is the formal step that triggers negotiation.

## Responsibilities

- Create proposal records tied to a Deal
- Store proposal content: scope, deliverables, timeline, pricing breakdown
- Version proposals (each revision is a distinct, immutable record)
- Track proposal status (draft, sent, accepted, rejected, expired)
- Generate a shareable read-only link for the client to review the proposal
- Record client response (accepted / rejected) with timestamp
- Coordinate with AI domain to generate proposal content from deal and client context

## Does Not Own

- Deal pipeline progression (owned by **Deals** domain; Proposals reports acceptance/rejection back)
- Contract creation from an accepted proposal (owned by **Contracts** domain, triggered by acceptance event)
- PDF rendering and delivery (delegated to **Workers** domain via PDF job)
- Client contact data (owned by **Clients** domain)

## Core Concepts

**Proposal** — The root aggregate. Has `proposal_id` (UUID), `deal_id`, `owner_user_id`, `version_number` (integer, starting at 1), `status`, `content`, `created_at`, `sent_at`, `responded_at`.

**Proposal Version** — Every time a proposal is revised after being sent, a new Proposal record is created with an incremented `version_number`. The previous version becomes read-only. Only one version per deal may be in `sent` or `pending_response` status at a time.

**Proposal Content** — A structured value object containing:
- `title`: proposal heading
- `executive_summary`: brief overview for the client
- `scope_of_work`: detailed deliverables list
- `timeline`: start date, end date, milestones
- `pricing`: line items (description, quantity, unit price), total, currency
- `terms`: payment terms, revision policy, IP ownership
- `notes`: optional freeform notes

**Proposal Status** — Tracks the document through its lifecycle:
- `draft` — Being written; not yet sent to client
- `sent` — Delivered to client; awaiting response
- `accepted` — Client confirmed acceptance
- `rejected` — Client declined
- `expired` — No response within expiry window (default: 14 days after sent)
- `superseded` — An older version replaced by a newer revision

**Shareable Link** — A tokenized, expiry-bound URL that allows the client (unauthenticated) to view the proposal. Does not grant any other system access.

## Business Rules

- A Proposal must belong to exactly one Deal. The `deal_id` is immutable once set.
- A Proposal can only be created for Deals in stages `qualified`, `proposal_sent`, or `in_negotiation`. Creating a proposal for a `new_lead` or terminal deal is rejected.
- Only one Proposal version may have `status: sent` per Deal at any time. Creating a new revision while one is sent automatically marks the previous as `superseded`.
- A `draft` proposal may be freely edited. Once `sent`, content becomes immutable.
- Accepting a Proposal automatically advances the parent Deal stage (if currently `proposal_sent`) to `in_negotiation`, via a domain event.
- Accepting a Proposal emits `proposals.proposal_accepted` which the **Contracts** domain listens to for contract scaffolding.
- A rejected or expired proposal does not automatically change the Deal stage; the freelancer decides next steps manually.
- AI-generated proposal content is treated as a draft; the user must review and confirm before the proposal status can move to `sent`.
- Pricing total must equal the sum of line items. The system validates this before allowing `sent` status.

## Lifecycle

```
[Proposal Created: draft]
         │
   User edits content (or AI generates draft)
         │
         ▼
      [draft] ──── User sends to client ────► [sent]
                                                 │
                             ┌───────────────────┼───────────────────┐
                             ▼                   ▼                   ▼
                        [accepted]          [rejected]          [expired]
                             │
                     Contracts domain creates Contract
                             │
                         [terminal]

   User revises while sent:
      [sent] ──► old version [superseded], new version [draft] → [sent]
```

## Relationships

| Related Domain | Nature |
|---|---|
| **Deals** | A Proposal belongs to one Deal. Proposal acceptance/rejection can update the Deal stage. |
| **Clients** | Proposal content references Client name and contact for personalization. Read-only reference. |
| **Contracts** | An accepted Proposal is the source document for a new Contract. |
| **AI** | AI Proposal Generator produces draft content; result is written back to Proposals as a draft. |
| **Workers** | PDF Workers render Proposal content to PDF for delivery and storage. |
| **Reminders** | Reminders may reference a Proposal (e.g. "follow up 3 days after sending"). |

## Events

| Event | Trigger | Consumers |
|---|---|---|
| `proposals.proposal_created` | New draft saved | Analytics (proposal count) |
| `proposals.proposal_sent` | Status changed to `sent` | Deals (advance stage to `proposal_sent`), Reminders (schedule follow-up) |
| `proposals.proposal_accepted` | Client accepts | Deals (advance to `in_negotiation`), Contracts (scaffold new contract), Analytics |
| `proposals.proposal_rejected` | Client declines | Deals (notify user), Reminders (cancel pending follow-ups) |
| `proposals.proposal_expired` | Expiry window passes without response | Reminders (notify freelancer), Analytics |
| `proposals.proposal_revised` | New version created | Previous version marked `superseded` |

## Permissions

| Actor | Allowed Actions |
|---|---|
| **Authenticated User** | Create, edit (draft only), send, and view own proposals; request AI generation |
| **Client (via shareable link)** | View proposal, submit accept/reject response — no authentication required |
| **Admin** | Read any proposal for support; cannot modify |
| **Anonymous** | None (except via valid shareable link) |

## Future Considerations

- E-signature integration (DocuSign, HelloSign) for legally binding acceptance
- Proposal templates: reusable structures for common project types
- Client comments/questions on the proposal view
- Proposal analytics: track link opens, time-on-page (requires pixel or redirect tracking)
- Multi-currency support with live exchange rate display
- Interactive pricing: client-selectable optional add-ons within the proposal
