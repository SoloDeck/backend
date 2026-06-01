# Subscription Aggregate

## Aggregate Root

**`Subscription`** — represents a user's current plan and their entitlements.

Every AI feature gate in the system runs through Subscription. One subscription per user, always. The Free plan is created automatically on user registration.

## Child Entities

| Entity | Relation | Table | Notes |
|--------|----------|-------|-------|
| `UsageRecord` | One-to-many | `usage_records` | Tracks AI generation consumption per period |
| `BillingEvent` | One-to-many (append-only) | `billing_events` | Immutable payment/upgrade history |

## Value Objects

| Value Object | Fields | Notes |
|-------------|--------|-------|
| `BillingPeriod` | `start`, `end` | Current active period for usage counting |
| `EntitlementSet` | `can_use_ai`, `can_export_pdf`, `max_clients`, `max_deals`, `max_ai_generations_per_month` | Derived from linked `SubscriptionPlan` |
| `StripeReference` | `stripe_subscription_id`, `stripe_customer_id` | External billing reference |

## Invariants

1. **One subscription per user** — enforced by `UNIQUE(user_id)`.
2. A `suspended` subscription blocks AI features and new content creation but allows read access to existing data.
3. Usage counters reset at `current_period_start` — not at subscription creation date.
4. `max_ai_generations_per_month` of `0` means unlimited (Free plan has a set limit; paid plans have higher limits or unlimited).
5. Billing events are append-only — never updated or deleted.
6. Admin overrides (`override_by_admin_id`, `override_expires_at`) allow temporary plan upgrades without affecting Stripe.
7. Plan changes take effect immediately — no prorating logic in current scope.

## Lifecycle

```
   active             ← created on user registration (Free plan)
     │
  (upgrade/downgrade via Stripe webhook)
     ▼
   active (new plan)
     │
  (payment failure)
     ▼
  past_due
     │
  (payment recovered)
     ▼
   active
     │
  (payment fails repeatedly)
     ▼
  suspended           ← AI and creation features blocked
     │
  (reactivated)
     ▼
   active
     │
  (user requests cancellation)
     ▼
  cancelled           ← no new access; data retained
```

## Commands

| Command | Actor | Preconditions |
|---------|-------|--------------|
| `CreateFreeSubscription` | System (on user_created) | No existing subscription for user |
| `UpgradePlan` | Owner / Stripe webhook | Valid plan slug |
| `DowngradePlan` | Owner / Stripe webhook | Valid plan slug |
| `SuspendSubscription` | System (payment failure) | Subscription is `active` or `past_due` |
| `ReactivateSubscription` | System (payment success) | Subscription is `suspended` or `past_due` |
| `CancelSubscription` | Owner | Subscription is `active` |
| `RecordUsage` | System (AI facade) | Subscription is `active` |
| `CheckEntitlement` | Any domain service | — (read-only check) |
| `AdminOverridePlan` | Admin | Override duration specified |

## Events

| Event | Payload | Consumers |
|-------|---------|-----------|
| `subscriptions.plan_changed` | `user_id`, `old_plan`, `new_plan` | Auth (re-issue JWT with new tier) |
| `subscriptions.suspended` | `user_id` | Auth (invalidate tokens), Admin |
| `subscriptions.reactivated` | `user_id` | Auth, Admin |
| `subscriptions.usage_limit_reached` | `user_id`, `feature` | None (error thrown at call site) |

## Persistence Considerations

- `UNIQUE(user_id)` ensures exactly one active subscription row.
- `usage_records` is reset conceptually by period — new records are inserted each period; old ones are not deleted (used for analytics).
- Billing events are append-only.
- `can_use_ai` check must be the first thing `AIFacade` does before any LLM call.

## Future Scaling Considerations

- Team plans (multiple users per subscription) would require a `subscription_members` table.
- Proration and credit tracking would require a `credit_ledger` child entity.
- Usage analytics dashboards would consume `usage_records` as an event log.
