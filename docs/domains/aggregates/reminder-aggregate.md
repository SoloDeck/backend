# Reminder Aggregate

## Aggregate Root

**`Reminder`** — a scheduled notification linked polymorphically to any business object.

Reminders are the notification backbone of SoloDesk. They do not own business objects — they target them. This loose coupling allows one reminder system to serve deals, proposals, contracts, and invoices without creating cross-domain FK dependencies.

## Child Entities

| Entity | Relation | Table | Notes |
|--------|----------|-------|-------|
| `ReminderDeliveryRecord` | One-to-many (append-only) | `reminder_delivery_records` | Each delivery attempt logged |

## Value Objects

| Value Object | Fields | Notes |
|-------------|--------|-------|
| `PolymorphicTarget` | `target_type`, `target_id` | Identifies the business object being reminded about |
| `RecurrenceRule` | `frequency`, `interval`, `end_date` | Optional — for repeating reminders |
| `DeliveryResult` | `channel`, `status`, `sent_at`, `error` | Stored per delivery attempt |

## Invariants

1. There is **no database FK** on `target_id` — referential integrity is enforced at the application layer. If the target is deleted, the reminder must be auto-cancelled via a domain event.
2. `target_type` must be one of: `deal`, `proposal`, `contract`, `invoice`.
3. A reminder in `cancelled` or `completed` status is **terminal**.
4. Delivery records are append-only — never updated or deleted.
5. When a target reaches a terminal state (deal `lost`/`completed_and_billed`, invoice `paid`/`cancelled`, etc.), all pending reminders for that target must be auto-cancelled.
6. Recurrence is only valid while status is `pending` — completed recurrences are converted to `completed`.

## Lifecycle

```
  pending            ← scheduled for future delivery
     │
  (scheduler fires)
     ▼
  delivering         ← in-flight (Worker picked it up)
     │
  ┌──┤
  │  │ (success)
  │  ▼
  │ delivered
  │  │
  │  │ (if recurring — next occurrence scheduled)
  │  ▼
  │ pending (next)   OR   completed (final occurrence)
  │
  │  (failure after retries)
  ├──▼
  │ failed
  │
  │  (target reaches terminal state / owner cancels)
  └──▼
   cancelled         ← terminal
```

## Commands

| Command | Actor | Preconditions |
|---------|-------|--------------|
| `CreateReminder` | Owner / System | Target exists (verified at app layer) |
| `UpdateReminder` | Owner | Reminder is `pending` |
| `CancelReminder` | Owner / System | Reminder is `pending` or `delivering` |
| `DeliverReminder` | Worker (Celery) | Reminder is `pending`, `scheduled_at` reached |
| `RecordDeliveryAttempt` | Worker | Always (success or failure) |
| `ScheduleNextOccurrence` | Worker | Reminder is recurring, not at end_date |

## Events

| Event | Payload | Consumers |
|-------|---------|-----------|
| `reminders.reminder_delivered` | `reminder_id`, `target_type`, `target_id`, `channel` | None |
| `reminders.reminder_failed` | `reminder_id`, `error` | Admin (monitoring) |
| `reminders.reminder_cancelled` | `reminder_id`, `reason` | None |

### Inbound Events (consumed by Reminders)

| Event Source | Event | Action |
|-------------|-------|--------|
| Deals | `deals.deal_closed` | Cancel all pending reminders for deal |
| Proposals | `proposals.proposal_accepted/rejected` | Cancel pending reminders for proposal |
| Contracts | `contracts.completed/terminated` | Cancel pending reminders for contract |
| Invoices | `invoices.invoice_paid/cancelled` | Cancel pending reminders for invoice |

## Persistence Considerations

- `reminder_delivery_records` is append-only.
- No FK on `target_id` — the `target_type` + `target_id` pair is verified only when the reminder is created.
- `scheduled_at` is indexed for efficient scheduler polling.
- Celery beat polls `reminders` every 60 seconds for due reminders.

## Future Scaling Considerations

- Multi-channel delivery (email, Zalo, in-app push) is designed into the delivery record schema.
- At high volume, a dedicated reminder queue (separate from AI jobs) prevents priority inversion.
- Reminder templates (pre-written messages) could be pulled from `system_templates`.
