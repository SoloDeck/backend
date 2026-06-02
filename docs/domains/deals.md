# Deals Domain

## Purpose

Track every sales opportunity a freelancer pursues from first contact through to completed billing. Deals are the central entity in SoloDesk's pipeline: they connect clients to the work being scoped, proposed, contracted, and invoiced.

## Responsibilities

- Create and manage deal records
- Enforce and track pipeline stage progression
- Record deal value (estimated and actual)
- Link deals to the client they belong to
- Maintain a timeline of deal activity (stage changes, notes)
- Provide pipeline view data (stage distribution, total value by stage)
- Trigger downstream workflows on stage transitions (e.g. proposal generation, contract creation)
- Provide an embeddable intake form (shareable link) for client self-submission of new leads

## Does Not Own

- Client profile and contact data (owned by **Clients** domain)
- Proposal documents (owned by **Proposals** domain)
- Contract documents (owned by **Contracts** domain)
- Invoice generation or payment tracking (owned by **Invoices** domain)
- Automated reminder scheduling (owned by **Reminders** domain)
- Revenue aggregation and reporting (owned by **Analytics** domain)
- AI-driven lead qualification logic (owned by **AI** domain)

## Core Concepts

**Deal** — The root aggregate. Represents a single sales opportunity. Has `deal_id` (UUID), `owner_user_id`, `client_id`, `title`, `stage`, `estimated_value`, `currency`, `source` (how the lead arrived), `notes`, `created_at`, `updated_at`, `closed_at`.

**Pipeline Stage** — An ordered enum representing where a deal stands in the sales process:
1. `new_lead` — Initial capture; unqualified
2. `qualified` — AI or manual qualification confirms fit
3. `proposal_sent` — A formal Proposal has been delivered to the client
4. `in_negotiation` — Client is reviewing; terms being discussed
5. `active` — Deal won; work in progress
6. `completed_and_billed` — Work delivered and Invoice issued

**Deal Source** — How the lead originated: `inbound`, `referral`, `outreach`, `platform` (e.g. Upwork), `other`.

**Activity Entry** — An immutable log of something that happened on a deal: stage change, note added, document attached. Append-only, tied to `deal_id`.

**Deal Value** — `estimated_value` is set early in the pipeline. `actual_value` is set at `completed_and_billed` stage (may differ from estimate).

## Business Rules

- A Deal must belong to exactly one Client. The `client_id` is set at creation and cannot be changed.
- Stage transitions are strictly forward with the following valid moves:

  | From | Allowed Next Stages |
  |---|---|
  | `new_lead` | `qualified`, `lost` |
  | `qualified` | `proposal_sent`, `lost` |
  | `proposal_sent` | `in_negotiation`, `lost` |
  | `in_negotiation` | `active`, `lost` |
  | `active` | `completed_and_billed`, `lost` |
  | `completed_and_billed` | _(terminal)_ |
  | `lost` | _(terminal)_ |

- `lost` is a terminal stage representing a deal that did not convert. It is not listed in the main pipeline stages but is a valid state.
- Transitioning to `active` requires at least one accepted Proposal linked to the Deal. If none exists, the transition is blocked.
- Transitioning to `completed_and_billed` requires at least one Invoice linked to the Deal.
- `estimated_value` may be zero or null early in the pipeline but must be set before moving to `proposal_sent`.
- A Deal in a terminal stage (`completed_and_billed` or `lost`) cannot be edited except to add Activity Entries or notes.
- Only the owning User can edit their own Deals.

## Lifecycle

```
[Deal Created: new_lead]
         │
   AI Qualification or manual review
         │
         ▼
    [qualified]
         │
   Proposal generated and sent
         │
         ▼
  [proposal_sent]
         │
   Client responds
         │
         ▼
  [in_negotiation]
         │
   Terms agreed, work begins
         │
         ▼
     [active]
         │
   Work delivered, invoice issued
         │
         ▼
[completed_and_billed] ←── terminal

At any non-terminal stage: ──► [lost] ←── terminal
```

## Relationships

| Related Domain | Nature |
|---|---|
| **Clients** | Each Deal belongs to one Client. Clients domain owns the client record; Deals only stores the reference. |
| **Proposals** | A Deal may have one or many Proposal versions. Proposals reference `deal_id`. |
| **Contracts** | A Contract is generated once a Proposal is accepted; references `deal_id`. |
| **Invoices** | One or more Invoices may be linked to a Deal (milestone billing). |
| **Reminders** | Reminders may target a Deal (e.g. follow up after `proposal_sent`). |
| **Analytics** | Analytics reads Deal stage and value data for pipeline metrics and revenue reporting. |
| **AI** | AI Lead Qualifier reads Deal data to assess and update qualification; result returned to Deals. |

## Events

| Event | Trigger | Consumers |
|---|---|---|
| `deals.deal_created` | New deal record saved | Analytics (pipeline count), AI (auto-qualify if enabled) |
| `deals.stage_changed` | Stage transition validated and applied | Reminders (reschedule follow-up), Analytics (pipeline funnel update), AI (trigger next step generation) |
| `deals.deal_lost` | Moved to `lost` stage | Analytics, Reminders (cancel pending deal reminders) |
| `deals.deal_completed` | Moved to `completed_and_billed` | Analytics (revenue contribution), Clients (update client status) |
| `deals.value_updated` | `estimated_value` or `actual_value` changed | Analytics (recalculate pipeline value) |
| `deals.note_added` | User adds a note or activity entry | No external consumer; internal audit trail |

## Permissions

| Actor | Allowed Actions |
|---|---|
| **Authenticated User** | Full CRUD on own deals, stage transitions, notes |
| **Admin** | Read any deal for support; cannot modify |
| **Anonymous** | None |

## Future Considerations

- Deal templates: pre-fill common deal types (fixed-price project, monthly retainer, hourly)
- Pipeline automation rules: auto-advance stage when certain conditions are met (e.g. proposal opened by client)
- Deal cloning: duplicate a deal as a starting point for a similar new opportunity
- Lost reason capture: structured dropdown of reasons for losing a deal, feeding Analytics
- Probability scoring per stage for weighted pipeline value forecasting
- Team deals: shared deals visible to multiple users (team accounts)
