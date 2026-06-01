# Analytics Domain

## Purpose

Aggregate and surface business performance metrics that help freelancers understand how their practice is growing, where deals are won or lost, and how revenue flows over time. Analytics is a read-only, derived domain: it never owns source records but computes insights from data produced by all other operational domains.

## Responsibilities

- Calculate and cache revenue metrics (total billed, received, outstanding)
- Track pipeline metrics (deal count per stage, total pipeline value, conversion rates)
- Calculate win rate (deals won vs. deals lost or total closed)
- Report on AI feature usage (generations used, outcomes)
- Provide period-over-period comparisons (monthly, quarterly, yearly)
- Provide per-client revenue breakdowns
- Expose a query API that the frontend dashboard consumes
- Maintain pre-aggregated snapshots to support fast dashboard loads

## Does Not Own

- Source business data (owned by Deals, Invoices, Clients, Contracts, etc.)
- Real-time pipeline management (owned by **Deals** domain)
- Billing or subscription management (owned by **Subscriptions** domain)
- Raw event storage or system audit logs (owned by **Admin** domain)

## Core Concepts

**Revenue Snapshot** — A point-in-time record of a user's revenue metrics for a given period (month/quarter/year): `period`, `total_invoiced`, `total_collected`, `total_outstanding`, `total_overdue`.

**Pipeline Snapshot** — A record of pipeline state at a point in time: `stage`, `deal_count`, `total_value`. Used for trend analysis.

**Win Rate** — The ratio of deals reaching `active` or `completed_and_billed` to all deals that reached a closing stage (`active`, `completed_and_billed`, or `lost`). Calculated per period.

**Funnel Conversion Rate** — The percentage of deals that advance from one stage to the next. Identifies which stage has the highest drop-off.

**Top Clients** — Ranked list of clients by total invoiced or collected revenue in a given period.

**AI Usage Metrics** — Aggregated counters per user: `proposals_generated`, `contracts_generated`, `leads_qualified`, `follow_ups_generated`. Used for both user dashboards and Admin cost monitoring.

**Dashboard Summary** — A pre-computed object returned in a single API call for the user dashboard: active deal count, pipeline value, monthly revenue, overdue invoice count, win rate.

## Business Rules

- Analytics data is derived exclusively from operational domain data. It must never be the authoritative record for any business fact.
- Analytics reads deal, invoice, and contract data via read-optimized queries or materialized views; it does not write to operational tables.
- Metrics are computed at query time for up-to-date figures or from pre-aggregated snapshots for historical periods. Snapshots are refreshed nightly or triggered by key events.
- All analytics are scoped strictly to the requesting user's own data. Cross-user data is never exposed to regular users.
- Deleted or voided records (voided invoices, lost deals) are excluded from forward-looking metrics but included in historical period data to maintain accuracy.
- Win rate denominator includes only deals that have reached a conclusive outcome (won or lost); open deals are excluded.
- Revenue is reported in the user's configured `currency`. Multi-currency conversion uses rates stored at invoice creation time.

## Lifecycle

Analytics does not have a lifecycle of its own. It passively listens to events from operational domains and refreshes snapshots accordingly.

```
Operational Events (Deals, Invoices, Contracts, etc.)
              │
              ▼
   [Analytics Event Consumer]
              │
   Updates pre-aggregated snapshots
              │
              ▼
   [Dashboard Query API]
              │
              ▼
   [Frontend Dashboard]
```

## Relationships

| Related Domain | Nature |
|---|---|
| **Deals** | Reads deal stages, values, and transitions for pipeline and funnel metrics. |
| **Invoices** | Reads invoice amounts and payment dates for revenue and cash flow metrics. |
| **Clients** | Reads client associations for per-client revenue breakdowns. |
| **Contracts** | Reads contract values and milestone data for contracted revenue projections. |
| **Subscriptions** | Reads plan tier distribution for Admin-level reporting (not exposed to users). |
| **AI** | Reads AI generation events for usage tracking. |
| **Users** | All analytics are user-scoped via `owner_user_id`. |

## Events

Analytics **consumes** events from other domains; it publishes no domain events of its own.

| Consumed Event | Source Domain | Analytics Action |
|---|---|---|
| `deals.deal_created` | Deals | Increment pipeline count |
| `deals.stage_changed` | Deals | Update stage distribution snapshot |
| `deals.deal_completed` | Deals | Update win rate, move to revenue pipeline |
| `deals.deal_lost` | Deals | Update win rate and funnel drop-off |
| `invoices.payment_recorded` | Invoices | Update revenue collected metric |
| `invoices.invoice_overdue` | Invoices | Update overdue count |
| `invoices.invoice_paid` | Invoices | Update collected revenue, clear overdue |
| `clients.client_created` | Clients | Update total client count |
| `subscriptions.plan_upgraded` | Subscriptions | Record upgrade event (Admin analytics) |

## Permissions

| Actor | Allowed Actions |
|---|---|
| **Authenticated User** | Read own dashboard summary, revenue metrics, pipeline metrics, per-client breakdown |
| **Admin** | Read aggregated platform-wide metrics (user count, MRR, AI usage costs, plan distribution) |
| **Anonymous** | None |

## Future Considerations

- Goal tracking: user sets a monthly revenue target; dashboard shows progress
- Forecast: project future revenue based on pipeline probability weighting
- Cohort analysis: when users joined vs. their revenue growth trajectory
- Export: download analytics data as CSV or PDF report
- Comparison with anonymized peer benchmarks ("freelancers in your category earn X on average")
- Real-time dashboard: WebSocket-based live updates instead of polling
- Custom date ranges and filters for all metrics
