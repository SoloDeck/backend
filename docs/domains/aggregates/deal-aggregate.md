# Deal Aggregate

## Aggregate Root

**`Deal`** — represents a sales opportunity in the freelancer's pipeline.

The Deal is the central business object of SoloDesk. It drives the stage machine, triggers AI qualification, and is the parent context for proposals, contracts, and invoices.

## Child Entities

| Entity | Relation | Table | Notes |
|--------|----------|-------|-------|
| `DealActivityEntry` | One-to-many (append-only) | `deal_activity_entries` | Immutable audit log |

## Value Objects

| Value Object | Fields | Notes |
|-------------|--------|-------|
| `DealValue` | `amount`, `currency` | Estimated deal value |
| `StageTransition` | `from_stage`, `to_stage`, `transitioned_at` | Captured in activity log |

## Invariants

1. `client_id` is **immutable** after creation — a deal cannot be reassigned to a different client.
2. Stage transitions are **forward-only** except for moving back to `in_negotiation` from `proposal_sent`.
3. `completed_and_billed` and `lost` are **terminal** — no further transitions permitted.
4. Transitioning to `active` requires at least one `accepted` Proposal linked to this deal.
5. Transitioning to `completed_and_billed` requires at least one `paid` or `sent` Invoice linked to this deal.
6. Moving to `lost` or `completed_and_billed` sets `closed_at` and triggers cancellation of all pending Reminders.
7. Activity log entries are append-only — never updated or deleted.

## Lifecycle

```
  new_lead
     │
  (AI qualification or manual advance)
     ▼
  qualified
     │
  (proposal created + sent)
     ▼
  proposal_sent
     │
  (client response)
     ▼
  in_negotiation
     │              ↑ (can return here from proposal_sent)
  (proposal accepted)
     ▼
   active           ← requires accepted Proposal
     │
  (work done + invoice sent)
     ▼
  completed_and_billed  ← terminal (requires Invoice)
     │
  (any stage)
     ▼
   lost             ← terminal (any time)
```

## Commands

| Command | Actor | Preconditions |
|---------|-------|--------------|
| `CreateDeal` | Owner | Client exists, not archived |
| `UpdateDeal` | Owner | Deal not terminal |
| `TransitionStage` | Owner | `Deal.can_transition_to(target)` returns true |
| `AddNote` | Owner | Deal not terminal |
| `QualifyWithAI` | Owner | `subscription.can_use_ai`, deal is `new_lead` or `qualified` |
| `CloseDeal` | Owner | Terminal stage selected |

## Events

| Event | Payload | Consumers |
|-------|---------|-----------|
| `deals.deal_created` | `deal_id`, `client_id`, `owner_user_id` | None currently |
| `deals.stage_transitioned` | `deal_id`, `old_stage`, `new_stage` | Reminders (auto-cancel if terminal) |
| `deals.deal_closed` | `deal_id`, `outcome` (won/lost) | Analytics (win rate), Reminders |
| `deals.ai_qualification_completed` | `deal_id`, `score`, `recommendation` | None (stored on deal) |

## Persistence Considerations

- Stage machine logic lives in `Deal.can_transition_to()` — pure Python, no DB.
- `deal_activity_entries` is append-only (no `updated_at`).
- `closed_at` is set server-side when terminal stage is reached.
- `owner_user_id` and `deleted_at` filters required on every query.

## Future Scaling Considerations

- Activity log could be replaced with an event-sourced stream for full audit.
- Deal scoring (probability-weighted pipeline) would be a natural analytics projection.
- For teams (multi-user), a `assignee_user_id` would be needed alongside `owner_user_id`.
