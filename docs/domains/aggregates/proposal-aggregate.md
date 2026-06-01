# Proposal Aggregate

## Aggregate Root

**`Proposal`** — a versioned document sent to a client to formalize the scope and price of a deal.

Proposals are the first formal deliverable in the SoloDesk pipeline. Each proposal is linked to exactly one deal and may be AI-generated or manually authored.

## Child Entities

None. Proposal content is a single document entity — line items and sections are stored as JSONB within the proposal row.

## Value Objects

| Value Object | Fields | Notes |
|-------------|--------|-------|
| `ProposalContent` | `sections[]`, `total_value`, `currency` | JSONB blob |
| `ShareToken` | `token`, `expires_at` | Allows client to view without auth |

## Invariants

1. `deal_id` is **immutable** after creation.
2. Only **one proposal per deal may be in `sent` status** at any time. Creating a new revision auto-supersedes the previous sent proposal.
3. Lifecycle is unidirectional: `draft → sent → accepted | rejected | expired`.
4. A proposal in `accepted`, `rejected`, or `expired` status is **terminal** — no further edits.
5. Only `draft` proposals may have their content edited.
6. AI-generated content always arrives as `draft` — the user must explicitly send it.
7. `accepted` status emits `proposals.proposal_accepted` event which may trigger deal stage advance.

## Lifecycle

```
   draft              ← created (manual or AI-generated)
     │
  (owner sends)
     ▼
   sent               ← only one per deal allowed
     │
  ┌──┤
  │  │ (client accepts)
  │  ▼
  │ accepted          ← terminal — triggers Contract creation
  │
  │  (client rejects)
  ├──▼
  │ rejected          ← terminal
  │
  │  (time passes without response)
  └──▼
   expired            ← terminal (can be set by scheduler)
```

## Commands

| Command | Actor | Preconditions |
|---------|-------|--------------|
| `CreateProposal` | Owner | Deal exists and not terminal |
| `GenerateProposalWithAI` | Owner | `subscription.can_use_ai`, deal is active |
| `EditProposal` | Owner | Proposal is `draft` |
| `SendProposal` | Owner | Proposal is `draft`, `total_value > 0` |
| `AcceptProposal` | Client / Owner | Proposal is `sent` |
| `RejectProposal` | Client / Owner | Proposal is `sent` |
| `ExpireProposal` | System (scheduler) | Proposal is `sent`, past expiry date |

## Events

| Event | Payload | Consumers |
|-------|---------|-----------|
| `proposals.proposal_created` | `proposal_id`, `deal_id` | None currently |
| `proposals.proposal_sent` | `proposal_id`, `deal_id` | Reminders (schedule follow-up) |
| `proposals.proposal_accepted` | `proposal_id`, `deal_id` | Deals (advance to `active`), Contracts |
| `proposals.proposal_rejected` | `proposal_id`, `deal_id` | Deals (potentially move to `lost`) |
| `proposals.proposal_expired` | `proposal_id`, `deal_id` | Reminders (cancel), Analytics |

## Persistence Considerations

- `proposal_versions` may be added later to track revision history (not in initial schema).
- Share token (`share_token`, `share_token_expires_at`) allows public-facing read-only access.
- Only one `sent` proposal per deal enforced by partial unique index.
- AI generation result stored as `draft` content — never committed directly to `sent`.

## Future Scaling Considerations

- Version history (proposal v1, v2, v3) would require a `proposal_revisions` child table.
- E-signature integration (DocuSign, VietSign) would attach to this aggregate.
- PDF rendering is handled by Workers — the proposal stores only structured JSONB content.
