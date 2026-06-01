# Invoices Domain

## Purpose

Generate, track, and reconcile the financial documents that a freelancer sends to clients requesting payment. Invoices close the money loop for completed work: they translate contract payment milestones into actionable billing records and track whether money has been received.

## Responsibilities

- Create invoice records tied to a Contract milestone or a Deal
- Store invoice line items, totals, taxes, and currency
- Track invoice payment status (unpaid, partially paid, paid, overdue, void)
- Record partial and full payment events with amounts and dates
- Generate a shareable invoice link for the client to review and acknowledge
- Calculate overdue invoices based on due date
- Coordinate with Workers domain for PDF invoice generation
- Provide revenue data to the Analytics domain

## Does Not Own

- Payment gateway processing (handled by external provider; Invoices records outcomes only)
- Contract terms or milestone definitions (owned by **Contracts** domain)
- Automated payment reminder scheduling (owned by **Reminders** domain)
- Subscription billing for SoloDesk's own SaaS fees (owned by **Subscriptions** domain)

## Core Concepts

**Invoice** — The root aggregate. Has `invoice_id` (UUID), `owner_user_id`, `client_id`, `contract_id` (nullable; invoices may exist outside a formal contract), `deal_id`, `invoice_number` (human-readable, sequential per user, e.g. `INV-2024-0042`), `status`, `issue_date`, `due_date`, `currency`, `line_items`, `subtotal`, `tax_rate`, `tax_amount`, `total`, `amount_paid`, `notes`.

**Line Item** — A value object: `description`, `quantity`, `unit_price`, `amount`. Invoices contain 1–N line items.

**Invoice Number** — Auto-generated sequential identifier per user. Format is user-configurable (prefix + year + sequence). Once issued, an invoice number is never reused, even if the invoice is voided.

**Invoice Status:**
- `draft` — Being prepared; not yet sent to client
- `sent` — Delivered to client; awaiting payment
- `partially_paid` — Some payment received, balance outstanding
- `paid` — Full balance settled
- `overdue` — `due_date` has passed with outstanding balance
- `void` — Cancelled; no payment expected. Creates an audit trail (not deleted)

**Payment Record** — An immutable entry recording a payment event: `amount`, `payment_date`, `payment_method` (`bank_transfer` | `cash` | `online` | `other`), `reference_note`. Append-only.

**Tax** — A percentage applied to the subtotal. Tax rate is configurable per user (e.g. 10% VAT for Vietnam). Tax is informational — SoloDesk does not file taxes.

## Business Rules

- An Invoice must be associated with either a `deal_id` or a `contract_id` (or both). A standalone invoice with no business context is not permitted.
- Invoice `total` must equal `subtotal + tax_amount`. The system validates this before `sent` status is allowed.
- `amount_paid` cannot exceed `total`. If a payment record would cause `amount_paid > total`, it is rejected.
- Status transitions:
  - `draft` → `sent`: user explicitly sends invoice
  - `sent` → `partially_paid` or `paid`: payment recorded
  - `partially_paid` → `paid`: remaining balance received
  - `sent` or `partially_paid` → `overdue`: triggered automatically when `due_date` passes with outstanding balance (system job)
  - `overdue` → `paid` or `partially_paid`: payment recorded despite overdue status
  - Any non-`paid` status → `void`: user explicitly voids
  - `paid` → void: not permitted (cannot void a settled invoice; create a credit note instead)
- A voided invoice cannot be un-voided. The `invoice_number` is retired.
- `invoice_number` is assigned at creation and never changes.
- An Invoice may exist for a milestone before the Contract is fully signed, to support advance deposit billing.
- Overdue status is set by a background job, not on-demand; there may be a short delay.

## Lifecycle

```
[Invoice Created: draft]
        │
  User prepares line items and due date
        │
        ▼
     [sent]  ◄── Sent to client (PDF link shared)
        │
   ┌────┴──────────────┐
   │                   │
   │           due_date passes, balance outstanding
   │                   │
   │                   ▼
   │               [overdue]
   │                   │
   │       Payment received (full or partial)
   ▼                   ▼
[paid] ◄──── [partially_paid] ──── further payment ──── [paid]

Any non-paid status ──────────────────────────────► [void]
```

## Relationships

| Related Domain | Nature |
|---|---|
| **Contracts** | An Invoice may be tied to a Contract payment milestone. Contract holds `invoice_id` per milestone once issued. |
| **Deals** | Invoices are associated with a Deal. Deal reaching `completed_and_billed` requires at least one Invoice. |
| **Clients** | Invoice is addressed to a Client. Client data is embedded by value at creation for immutability. |
| **Reminders** | Reminders domain listens for `invoices.invoice_overdue` to schedule payment chase messages. |
| **Analytics** | Analytics reads Invoice `amount_paid` and dates for revenue reporting and cash flow analysis. |
| **Workers** | PDF Workers render the Invoice to PDF for delivery and storage. |

## Events

| Event | Trigger | Consumers |
|---|---|---|
| `invoices.invoice_created` | Draft saved | Analytics |
| `invoices.invoice_sent` | Status → `sent` | Reminders (schedule payment due reminder) |
| `invoices.payment_recorded` | Payment entry added | Analytics (revenue update), Contracts (update milestone status) |
| `invoices.invoice_paid` | `amount_paid` reaches `total` | Deals (update last-paid date), Analytics, Reminders (cancel pending payment reminders) |
| `invoices.invoice_overdue` | Background job detects overdue | Reminders (trigger payment chase), Analytics |
| `invoices.invoice_voided` | User voids invoice | Contracts (detach from milestone), Analytics |

## Permissions

| Actor | Allowed Actions |
|---|---|
| **Authenticated User** | Create, edit (draft only), send, record payment, void own invoices |
| **Client (via shareable link)** | View invoice — no payment action via SoloDesk (payment made externally) |
| **Admin** | Read any invoice for support; cannot modify |
| **Anonymous** | None (except via valid shareable link) |

## Future Considerations

- Credit notes: formal document to reverse or partially refund an invoice
- Recurring invoices: auto-generate monthly invoices for retainer contracts
- Payment gateway integration: direct in-app payment (Stripe, VNPay, MoMo)
- Multi-currency invoices with locked exchange rates
- Tax report export: aggregate tax amounts for a period to assist VAT filing
- Invoice reminders automation: configurable rule (e.g. send reminder 3 days before due, 1 day after overdue)
- Batch invoicing: generate multiple invoices from contract milestones in one action
