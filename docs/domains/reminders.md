# Reminders Domain

## Purpose

Schedule and deliver timely, contextual notifications that prompt the freelancer (and sometimes the client) to take action. Reminders prevent deals from going cold, invoices from going unpaid, and contracts from stalling — by surfacing the right nudge at the right moment.

## Responsibilities

- Create reminder records targeting a specific business object (Deal, Client, Invoice, Contract)
- Schedule reminders at an absolute datetime or relative to a business event (e.g. "3 days after proposal sent")
- Deliver notifications via configured channels (in-app, email)
- Track reminder delivery status (pending, sent, failed, cancelled)
- Cancel or reschedule reminders when the underlying situation changes
- Delegate actual delivery execution to the Workers domain (Celery jobs)
- Support recurring reminders (e.g. weekly follow-up until responded)

## Does Not Own

- The business objects being reminded about (owned by respective domains)
- Email delivery implementation (delegated to Workers via SendGrid adapter in `src/integrations/sendgrid/`)
- Zalo OA message delivery implementation (delegated to Workers via Zalo OA adapter in `src/integrations/zalo_oa/`)
- Push notification infrastructure (future; delegated to Workers)
- Subscription billing reminders for SoloDesk itself (owned by **Subscriptions** domain)

## Core Concepts

**Reminder** — The root aggregate. Has `reminder_id` (UUID), `owner_user_id`, `target_type` (`deal` | `client` | `invoice` | `contract`), `target_id`, `reminder_type`, `channel`, `scheduled_at`, `status`, `message_preview`, `recurrence_rule`.

**Reminder Type** — A named category that determines the default message template and suggested timing:
- `follow_up` — Check in on a deal or client
- `proposal_follow_up` — Follow up after sending a proposal
- `contract_signing_nudge` — Remind client to sign a contract
- `payment_due` — Invoice payment due soon
- `payment_overdue` — Invoice payment is past due
- `re_engagement` — Reach out to an inactive client
- `custom` — User-defined message and timing

**Reminder Status:**
- `pending` — Scheduled, not yet executed
- `sent` — Successfully delivered
- `failed` — Delivery attempt failed (will retry up to configured limit)
- `cancelled` — Explicitly cancelled (e.g. deal was closed, invoice was paid)
- `skipped` — Condition no longer applicable at fire time (e.g. invoice already paid)

**Recurrence Rule** — An optional RRULE-compatible definition for repeating reminders (e.g. every 3 days, until cancelled). Used for persistent follow-up sequences.

**Channel** — Where the notification is delivered: `in_app` (notification center), `email` (via SendGrid), `zalo` (via Zalo Official Account API), or `both`. Channel is chosen per user preference stored in their profile.

**Delivery Record** — An immutable log entry per delivery attempt: `attempted_at`, `channel`, `outcome`, `error_message`.

## Business Rules

- A Reminder must reference a valid `target_type` and `target_id`. The target must belong to the same `owner_user_id` as the Reminder.
- `scheduled_at` must be in the future at creation time (cannot schedule a reminder in the past).
- When a targeted business object reaches a terminal state (invoice paid, deal closed, contract completed), all `pending` reminders for that object are automatically cancelled.
- A Reminder in `sent` or `cancelled` status cannot be rescheduled; a new Reminder must be created.
- Failed reminders retry up to 3 times with exponential backoff before moving to `failed`.
- Recurring reminders auto-create the next instance upon successful delivery, per the recurrence rule, until cancelled or the recurrence end date is reached.
- AI-generated follow-up content may be suggested as the `message_preview`; the user may edit before the first send.
- Reminders must respect the user's configured `timezone` from their profile.
- Reminders do not send outside the user's configured working hours window unless the user explicitly overrides.

## Lifecycle

```
[Reminder Created: pending]
        │
  scheduled_at arrives → Worker picks up job
        │
        ▼
   Delivery attempt
        │
     ┌──┴────────┐
     ▼           ▼
  [sent]      [failed]
     │             │
  Recurring?   Retry (≤3 times)
     │             │
     ▼         [failed] (permanent)
  Next instance
  created [pending]

  At any time while [pending]:
     ├── Target object resolved → [cancelled]
     └── User cancels          → [cancelled]
```

## Relationships

| Related Domain | Nature |
|---|---|
| **Deals** | Reminders can target Deals. Deal stage changes may create or cancel reminders automatically. |
| **Clients** | Reminders can target Clients (e.g. re-engagement). Client archival cancels pending reminders. |
| **Invoices** | Reminders can target Invoices. Invoice payment cancels payment-related reminders. |
| **Contracts** | Reminders can target Contracts (e.g. signing nudge). Contract activation cancels signing reminders. |
| **Users** | Reminders are scoped to a User and use their timezone/notification preferences. |
| **Workers** | Workers execute the actual delivery of reminder notifications via Celery jobs. |
| **AI** | AI Follow-up Generator may produce the suggested message content for a reminder. |

## Events

| Event | Trigger | Consumers |
|---|---|---|
| `reminders.reminder_created` | New reminder saved | Workers (schedule Celery job) |
| `reminders.reminder_sent` | Delivery confirmed | Audit log; recurring: create next instance |
| `reminders.reminder_failed` | Delivery failed | Workers (schedule retry), Admin (alert if persistent failure) |
| `reminders.reminder_cancelled` | Explicit cancel or auto-cancel | Workers (revoke pending Celery job) |
| `reminders.reminder_skipped` | Condition no longer valid at fire time | Audit log |

## Permissions

| Actor | Allowed Actions |
|---|---|
| **Authenticated User** | Create, view, edit (pending only), cancel own reminders |
| **Admin** | View any reminder for support; can cancel stuck reminders |
| **Anonymous** | None |
| **System (Workers)** | Mark reminders as sent, failed, or skipped |

## Future Considerations

- AI-suggested reminder schedule: AI proposes an optimal follow-up sequence for a deal based on historical win patterns
- Client-facing reminders: send payment reminders directly to the client's email (as opposed to reminding the freelancer)
- Mobile push notifications
- SMS delivery channel
- Reminder templates: named sequences (e.g. "5-touch proposal follow-up") that can be applied to any deal with one click
- Snooze functionality: user can delay a reminder by N days directly from the notification
