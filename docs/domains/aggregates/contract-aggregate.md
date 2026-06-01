# Contract Aggregate

## Aggregate Root

**`Contract`** — a legally binding document created from an accepted proposal.

Contracts formalize the deal. They capture the client snapshot at signing time (immutable), define payment milestones, and trigger invoice creation via domain events.

## Child Entities

| Entity | Relation | Table | Notes |
|--------|----------|-------|-------|
| `ContractPaymentMilestone` | One-to-many | `contract_payment_milestones` | Each milestone can trigger an Invoice |

## Value Objects

| Value Object | Fields | Notes |
|-------------|--------|-------|
| `ClientSnapshot` | `name`, `email`, `phone`, `address`, `company` | Copied from Client at creation, never updated |
| `SignatureRecord` | `signer`, `signed_at`, `ip_address` | Recorded per signing event |
| `ShareToken` | `token`, `expires_at` | Allows client to view/sign without auth |

## Invariants

1. `deal_id` and `proposal_id` are **immutable** once set.
2. `client_snapshot` is populated at creation from the live client record and **never updated afterward** — contracts reflect the client as they were at signing time.
3. Only **one contract may be `active` or `pending_signatures` per deal** — enforced by partial unique index `contracts_one_active_per_deal`.
4. Content may only be edited while the contract is in `draft` status.
5. Transitioning to `signed` requires both parties to have signed (or owner-only depending on configuration).
6. `terminated` and `completed` are terminal — no further state changes.
7. A `ContractPaymentMilestone` emits `contracts.milestone_reached` when marked complete, which triggers Invoice creation.

## Lifecycle

```
   draft              ← created from accepted Proposal (or manual)
     │
  (owner sends for signature)
     ▼
  pending_signatures
     │
  (all signatures collected)
     ▼
   signed             ← active contract
     │
  (work delivered per milestones)
     ▼
  completed           ← terminal
     │
  (dispute / early end)
  terminated          ← terminal
```

## Commands

| Command | Actor | Preconditions |
|---------|-------|--------------|
| `CreateContract` | Owner | Linked proposal is `accepted` |
| `GenerateContractWithAI` | Owner | `subscription.can_use_ai` |
| `EditContract` | Owner | Contract is `draft` |
| `SendForSignature` | Owner | Contract is `draft` |
| `SignContract` | Owner / Client | Contract is `pending_signatures` |
| `AddPaymentMilestone` | Owner | Contract is `draft` or `signed` |
| `MarkMilestoneComplete` | Owner | Milestone not already completed |
| `TerminateContract` | Owner | Contract is `signed` |

## Events

| Event | Payload | Consumers |
|-------|---------|-----------|
| `contracts.contract_created` | `contract_id`, `deal_id`, `proposal_id` | None |
| `contracts.signed` | `contract_id`, `deal_id` | Deals (may advance stage) |
| `contracts.milestone_reached` | `contract_id`, `milestone_id`, `amount` | Invoices (create milestone invoice) |
| `contracts.completed` | `contract_id`, `deal_id` | Analytics |
| `contracts.terminated` | `contract_id`, `deal_id` | Reminders (cancel), Analytics |

## Persistence Considerations

- `client_snapshot` stored as JSONB — point-in-time copy, never joins to `clients` for display.
- Partial unique index on `(deal_id, status) WHERE status IN ('active', 'pending_signatures')`.
- `contract_payment_milestones` child table; delete cascades with contract.
- AI-generated contract content is always stored as `draft` first.

## Future Scaling Considerations

- E-signature provider integration (DocuSign, local providers) attaches here.
- Contract amendment versioning would require a `contract_amendments` child table.
- Template library (`system_templates`) can pre-populate contract structure.
