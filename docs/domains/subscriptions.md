# Subscriptions Domain

## Purpose

Define and enforce what each user is allowed to do within SoloDesk based on their subscription tier. This domain manages plan definitions, user entitlements, and usage tracking, ensuring that premium features remain gated and billing stays accurate.

## Responsibilities

- Define subscription plans and their feature entitlements
- Assign and manage a subscription record per user
- Track usage counters (e.g. AI generations used this billing cycle)
- Enforce usage limits at the service boundary
- Manage plan upgrades, downgrades, and cancellations
- Record billing events (payment received, payment failed, subscription renewed)
- Provide entitlement check API used by other domains

## Does Not Own

- User account data (owned by **Users** domain)
- Payment gateway integration and raw payment processing (owned by external billing provider, e.g. Stripe; this domain stores outcomes only)
- Invoice generation for freelancer-to-client billing (owned by **Invoices** domain)
- Authentication or access token issuance (owned by **Auth** domain)

## Core Concepts

**Plan** — A named tier of access (e.g. `Free`, `Pro`, `Agency`). Defines feature flags and numeric limits. Immutable from a business perspective; new tiers are added, existing ones are versioned.

**Subscription** — The active relationship between a User and a Plan. One subscription per user. Contains `plan_id`, `status`, `current_period_start`, `current_period_end`, `cancel_at_period_end`.

**Entitlement** — A named permission or limit derived from the Plan (e.g. `ai_generations_per_month: 10`, `can_export_pdf: true`). Entitlements are checked by other domains via the Subscriptions service.

**Usage Record** — A per-billing-cycle counter of consumed entitlements (e.g. `ai_generations_used: 4`). Resets at the start of each billing period.

**Billing Event** — An immutable record of a payment outcome: `payment_succeeded`, `payment_failed`, `subscription_renewed`, `subscription_cancelled`.

## Business Rules

- Every user starts on the `Free` plan upon account creation.
- AI generation features (Proposal, Contract, Lead Qualification) require a subscription with `can_use_ai: true`. Free plan users are blocked.
- Usage limits are enforced before the action is executed, not after. A user at their AI generation limit receives a `402 Payment Required` response with an upgrade prompt.
- Usage counters reset to zero at the start of each new billing period.
- A cancelled subscription remains active until `current_period_end`, then transitions to `Free`.
- Downgrading from a higher tier to a lower tier takes effect at the next billing period; the user retains higher-tier access until then.
- Upgrades take effect immediately; the billing period restarts.
- A `suspended` billing status (payment failed, grace period exceeded) blocks AI features but not read access to existing data.

## Lifecycle

```
[User Created]
      │
      ▼
[Subscription: Free plan, status: active]
      │
      ├─ User upgrades ────────────────────► [Plan: Pro, status: active]
      │                                             │
      │                                    Payment fails (retry window)
      │                                             │
      │                                    [status: past_due]
      │                                             │
      │                                    Grace period exceeded
      │                                             │
      │                                    [status: suspended]
      │                                             │
      │                                    Payment recovered / User downgrades
      │                                             │
      │                               [status: active / plan: Free]
      │
      └─ User cancels ─────────────────────► [cancel_at_period_end: true]
                                                    │
                                          Period ends
                                                    │
                                          [Plan: Free, status: active]
```

## Relationships

| Related Domain | Nature |
|---|---|
| **Users** | One subscription per user. Subscriptions references `user_id`. |
| **Auth** | Auth embeds `subscription_tier` in JWT at login using latest subscription record. |
| **AI** | AI domain checks entitlements before running any generation chain. |
| **Admin** | Admin can manually override subscription status or grant temporary plan upgrades. |
| **Analytics** | Analytics reports on subscription conversion rates and MRR. |

## Events

| Event | Trigger | Consumers |
|---|---|---|
| `subscriptions.plan_upgraded` | User moves to a higher tier | Auth (re-issue token with new tier), Admin (audit) |
| `subscriptions.plan_downgraded` | User moves to a lower tier | Admin (audit) |
| `subscriptions.cancelled` | User cancels subscription | Reminders (cancel upsell reminders) |
| `subscriptions.payment_succeeded` | Billing provider confirms payment | Admin (billing log) |
| `subscriptions.payment_failed` | Billing provider reports failure | Reminders (payment failure notification to user) |
| `subscriptions.suspended` | Grace period exceeded | Auth (invalidate token, force re-login with updated claims) |
| `subscriptions.usage_limit_reached` | Counter hits plan max | Users (notify user to upgrade) |

## Permissions

| Actor | Allowed Actions |
|---|---|
| **Authenticated User** | View own subscription and usage, upgrade/downgrade plan, cancel plan |
| **Admin** | View any subscription, manually override plan/status, grant promotional access |
| **Anonymous** | None |

## Future Considerations

- Team billing: one subscription shared across multiple team members with seat-based limits
- Metered billing: pay-per-AI-generation beyond a base allowance
- Annual vs monthly billing with discount pricing
- Promotional codes and trial periods
- Stripe webhook integration for real-time billing event processing
- Grandfathered plans: users on old pricing kept on legacy plan until they change
