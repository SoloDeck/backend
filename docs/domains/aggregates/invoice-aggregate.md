# Invoice Aggregate

## Aggregate Root

**`Invoice`** — a financial document issued to a client requesting payment.

Invoices are the financial tail of the pipeline. They may be created manually, triggered by contract milestones, or linked directly to a deal. Every invoice must be traceable to a contract or a deal.

## Child Entities

| Entity | Relation | Table | Notes |
|--------|----------|-------|-------|
| `InvoiceLineItem` | One-to-many | `invoice_line_items` | Description, quantity, unit price |
| `InvoicePaymentRecord` | One-to-many (append-only) | `invoice_payment_records` | Immutable payment events |

## Value Objects

| Value Object | Fields | Notes |
|-------------|--------|-------|
| `Money` | `amount`, `currency` | Used for `subtotal`, `tax_amount`, `total`, `amount_paid` |
| `ShareToken` | `token`, `expires_at` | Client can view invoice without auth |
| `TaxDetail` | `rate`, `amount` | Applied before `sent` status |

## Invariants

1. An invoice must be linked to `contract_id` **or** `deal_id` (or both) — **never standalone**.
2. `total = subtotal + tax_amount` — validated before transitioning to `sent` status.
3. `amount_paid` **cannot exceed** `total` — validated on every `InvoicePaymentRecord` insertion.
4. Once `paid`, the invoice is terminal — no further payment records or edits.
5. `cancelled` and `paid` are terminal statuses.
6. Line items may only be edited while invoice is `draft`.
7. Payment records are append-only — never updated or deleted.

## Lifecycle

```
   draft              ← created (manual or from milestone event)
     │
  (owner reviews and sends)
     ▼
   sent               ← client is notified
     │
  ┌──┤
  │  │ (partial payment)
  │  ▼
  │ partial_paid      ← amount_paid < total
  │  │
  │  │ (final payment)
  │  ▼
  │  paid             ← terminal (amount_paid == total)
  │
  │  (past due date)
  ├──▼
  │ overdue           ← scheduler sets this; may trigger Reminder
  │  │
  │  │ (payment received)
  │  ▼
  │  paid             ← terminal
  │
  │  (owner cancels)
  └──▼
   cancelled          ← terminal
```

## Commands

| Command | Actor | Preconditions |
|---------|-------|--------------|
| `CreateInvoice` | Owner / System (milestone event) | `contract_id` or `deal_id` must be set |
| `AddLineItem` | Owner | Invoice is `draft` |
| `RemoveLineItem` | Owner | Invoice is `draft` |
| `SetTax` | Owner | Invoice is `draft` |
| `SendInvoice` | Owner | `total = subtotal + tax_amount`, at least one line item |
| `RecordPayment` | Owner | Invoice is `sent`, `partial_paid`, or `overdue`; amount ≤ remaining balance |
| `MarkOverdue` | System (scheduler) | Invoice is `sent`, past `due_date` |
| `CancelInvoice` | Owner | Invoice is `draft` or `sent` |

## Events

| Event | Payload | Consumers |
|-------|---------|-----------|
| `invoices.invoice_created` | `invoice_id`, `deal_id`, `contract_id` | Reminders (schedule due-date reminder) |
| `invoices.invoice_sent` | `invoice_id`, `amount` | None |
| `invoices.payment_recorded` | `invoice_id`, `amount_paid`, `remaining` | Analytics |
| `invoices.invoice_paid` | `invoice_id`, `deal_id` | Deals (may trigger `completed_and_billed`), Analytics |
| `invoices.invoice_overdue` | `invoice_id`, `days_overdue` | Reminders (escalate), Analytics |

## Persistence Considerations

- `invoice_payment_records` is append-only (no `updated_at`).
- `amount_paid` is a derived sum — but stored as a denormalized column for performance. Must be kept in sync on every payment insertion.
- Share token allows public read-only access for client payment pages.
- `owner_user_id` filter on every repository query.

## Future Scaling Considerations

- Recurring invoices (subscription billing) would require a `recurrence_rule` field.
- Online payment gateway integration (MoMo, VNPay, Stripe) would attach payment confirmation webhooks here.
- PDF generation is handled by Workers — invoice stores structured data only.
