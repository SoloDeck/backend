# Client Aggregate

## Aggregate Root

**`Client`** — represents a business contact managed by a freelancer.

Clients are the entry point of the SoloDesk sales pipeline. Every deal, proposal, contract, and invoice traces back to a client.

## Child Entities

| Entity | Relation | Table | Notes |
|--------|----------|-------|-------|
| `ClientTag` | One-to-many | `client_tags` | Free-form label; max 20 per client |
| `ClientCommunicationLog` | One-to-many (append-only) | `client_communication_logs` | Immutable audit trail |

## Value Objects

| Value Object | Fields | Notes |
|-------------|--------|-------|
| `ContactInfo` | `email`, `phone`, `address`, `website` | Embedded in `clients` row |
| `Tag` | `name` | Normalized lowercase string |

## Invariants

1. `email` is unique **per owner** (`UNIQUE(owner_user_id, email)`) — not globally unique. The same client email may appear under different freelancers.
2. `status` is a forward-only progression for business purposes: `lead → active → inactive`. Archived clients (`archived`) are terminal for the pipeline.
3. A client may only be soft-deleted by their owner.
4. Communication logs are append-only — no `UPDATE` or `DELETE` on `client_communication_logs`.
5. Tags are limited to 20 per client (enforced at application layer).

## Lifecycle

```
     lead           ← initial status on creation
      │
  (qualification)
      ▼
    active          ← has ongoing deals
      │
  (no activity)
      ▼
   inactive
      │
  (re-engagement)
      ▼
    active
      │
  (archive)
      ▼
   archived         (terminal — no new deals allowed)
```

## Commands

| Command | Actor | Preconditions |
|---------|-------|--------------|
| `CreateClient` | Owner | Email unique within owner scope |
| `UpdateClient` | Owner | Client not archived, not deleted |
| `AddTag` | Owner | Tag count < 20 |
| `RemoveTag` | Owner | Tag exists on client |
| `LogCommunication` | Owner | Client exists and not deleted |
| `ChangeStatus` | Owner | Valid lifecycle transition |
| `ArchiveClient` | Owner | No open deals linked |
| `DeleteClient` | Owner | Soft-delete only |

## Events

| Event | Payload | Consumers |
|-------|---------|-----------|
| `clients.client_created` | `client_id`, `owner_user_id` | None currently |
| `clients.status_changed` | `client_id`, `old_status`, `new_status` | Reminders (cancel if archived) |
| `clients.client_deleted` | `client_id`, `owner_user_id` | Deals, Reminders |

## Persistence Considerations

- `clients` table is soft-deletable (`deleted_at`).
- `client_communication_logs` is append-only: no `updated_at` column.
- `client_tags` rows are owned exclusively by the client — delete cascades when client is hard-deleted.
- `owner_user_id` filter must appear on every repository query (multi-tenant isolation).

## Future Scaling Considerations

- Communication logs may grow large; consider archiving to cold storage after 12 months.
- Tags could become a managed taxonomy (admin-defined labels) for advanced filtering.
- A `client_score` field (derived from deal win rate) would be a good analytics projection.
