# Physical ERD — SoloDesk (PostgreSQL)

## Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Primary keys | UUID v4 (`gen_random_uuid()`) | Globally unique, safe to expose, no sequential enumeration |
| Tenant isolation | `owner_user_id` column on every user-owned table | Multi-tenant row-level filter; no schema-per-tenant overhead |
| Soft delete | `deleted_at TIMESTAMPTZ NULL` on User, Client, Deal | Compliance retention; FK integrity |
| Audit fields | `created_at`, `updated_at` via trigger on all mutable tables | Consistent; application cannot forget to update |
| Immutable logs | `created_at` only (no `updated_at`) | Append-only semantics enforced at DB level by omission |
| JSONB for content | `content`, `client_snapshot`, `metadata` as JSONB | Schema-flexible structured data; GIN-indexable |
| Enums | PostgreSQL `CREATE TYPE … AS ENUM` | Enforced at DB level; readable in queries |
| Arrays | `TEXT[]` for skills, `UUID[]` for feature flag targets | Avoids join tables for simple list values |
| Money | `NUMERIC(15,2)` for amounts, `NUMERIC(5,4)` for tax rates | Exact decimal arithmetic; no floating-point errors |
| Tokens | Store SHA-256 hash only, never raw token | Security: hash is worthless without the original |
| Client snapshot | JSONB embedded in Contract and Invoice | Immutability: contract/invoice data frozen at creation |
| Polymorphic FK | (`target_type`, `target_id`) in Reminder | Avoids four nullable FK columns; enforced at app layer |
| Analytics tables | Separate snapshot tables, not views | Pre-aggregated for fast dashboard reads |
| Indexes | Covering indexes on all tenant-filter + status query patterns | Expected hot paths: listing by owner + status |

---

## PostgreSQL Enums

```sql
CREATE TYPE user_role            AS ENUM ('freelancer', 'admin');
CREATE TYPE user_status          AS ENUM ('active', 'suspended', 'deleted');
CREATE TYPE notification_channel AS ENUM ('email', 'in_app', 'both');
CREATE TYPE theme_preference     AS ENUM ('light', 'dark');
CREATE TYPE subscription_status  AS ENUM ('active', 'past_due', 'suspended', 'cancelled');
CREATE TYPE billing_event_type   AS ENUM ('payment_succeeded', 'payment_failed', 'subscription_renewed', 'subscription_cancelled');
CREATE TYPE client_type          AS ENUM ('individual', 'company');
CREATE TYPE client_status        AS ENUM ('prospect', 'active', 'inactive', 'archived');
CREATE TYPE comm_channel         AS ENUM ('email', 'phone', 'meeting', 'message');
CREATE TYPE deal_stage           AS ENUM ('new_lead', 'qualified', 'proposal_sent', 'in_negotiation', 'active', 'completed_and_billed', 'lost');
CREATE TYPE deal_source          AS ENUM ('inbound', 'referral', 'outreach', 'platform', 'other');
CREATE TYPE deal_activity_type   AS ENUM ('stage_change', 'note_added', 'document_attached', 'ai_qualification');
CREATE TYPE ai_recommendation    AS ENUM ('qualify', 'pass');
CREATE TYPE proposal_status      AS ENUM ('draft', 'sent', 'accepted', 'rejected', 'expired', 'superseded');
CREATE TYPE contract_status      AS ENUM ('draft', 'pending_signatures', 'active', 'completed', 'terminated', 'expired');
CREATE TYPE invoice_status       AS ENUM ('draft', 'sent', 'partially_paid', 'paid', 'overdue', 'void');
CREATE TYPE payment_method       AS ENUM ('bank_transfer', 'cash', 'online', 'other');
CREATE TYPE reminder_target_type AS ENUM ('deal', 'client', 'invoice', 'contract');
CREATE TYPE reminder_type_enum   AS ENUM ('follow_up', 'proposal_follow_up', 'contract_signing_nudge', 'payment_due', 'payment_overdue', 're_engagement', 'custom');
CREATE TYPE reminder_status      AS ENUM ('pending', 'sent', 'failed', 'cancelled', 'skipped');
CREATE TYPE reminder_outcome     AS ENUM ('success', 'failure');
CREATE TYPE template_type        AS ENUM ('proposal', 'contract');
CREATE TYPE ai_module_type       AS ENUM ('lead_qualifier', 'proposal_generator', 'contract_generator', 'followup_generator');
CREATE TYPE ai_generation_status AS ENUM ('pending', 'completed', 'failed');
CREATE TYPE period_type          AS ENUM ('monthly', 'quarterly', 'yearly');
```

---

## Table Definitions with Indexes and Constraints

### `users`

```
PRIMARY KEY:  id
UNIQUE:       email
INDEX:        status, deleted_at  (filter active users)
TRIGGER:      updated_at auto-update
```

**Storage:** Inline professional profile and preferences as columns (no sub-table). Low cardinality, always fetched together.

### `oauth_identities`

```
PRIMARY KEY:  id
UNIQUE:       (provider, provider_sub)
INDEX:        user_id
```

### `refresh_tokens`

```
PRIMARY KEY:  id
UNIQUE:       token_hash
INDEX:        user_id, expires_at, revoked_at  (lookup valid tokens)
```

**Housekeeping:** Expired tokens (expires_at < NOW()) may be purged by a scheduled job.

### `password_reset_tokens`

```
PRIMARY KEY:  id
UNIQUE:       token_hash
INDEX:        user_id, expires_at
```

### `token_blacklist`

```
PRIMARY KEY:  id
UNIQUE:       jti
INDEX:        expires_at  (TTL-based cleanup job)
```

**Housekeeping:** Entries where `expires_at < NOW()` can be safely deleted — the JWT is already expired so blacklist entry is redundant.

---

### `subscription_plans`

```
PRIMARY KEY:  id
UNIQUE:       name, slug
INDEX:        is_active
```

### `subscriptions`

```
PRIMARY KEY:  id
UNIQUE:       user_id  (enforces one-subscription-per-user)
UNIQUE:       stripe_subscription_id (WHERE NOT NULL)
INDEX:        plan_id, status
INDEX:        current_period_end  (for renewal jobs)
TRIGGER:      updated_at auto-update
```

### `usage_records`

```
PRIMARY KEY:  id
UNIQUE:       (user_id, billing_period_start)
INDEX:        subscription_id
TRIGGER:      updated_at auto-update
```

### `billing_events`

```
PRIMARY KEY:  id
UNIQUE:       stripe_event_id (WHERE NOT NULL)
INDEX:        user_id, occurred_at DESC
INDEX:        subscription_id
```

---

### `clients`

```
PRIMARY KEY:  id
UNIQUE:       (owner_user_id, email) WHERE deleted_at IS NULL
INDEX:        owner_user_id, status  (tenant list + status filter)
INDEX:        owner_user_id, deleted_at  (exclude soft-deleted)
INDEX:        owner_user_id, name text_pattern_ops  (name search)
TRIGGER:      updated_at auto-update
```

### `client_tags`

```
PRIMARY KEY:  id
UNIQUE:       (client_id, tag)
INDEX:        client_id
```

**Constraint:** Application enforces ≤ 10 tags per client.

### `client_communication_logs`

```
PRIMARY KEY:  id
INDEX:        client_id, communicated_at DESC
INDEX:        owner_user_id  (tenant audit queries)
```

---

### `deals`

```
PRIMARY KEY:  id
INDEX:        owner_user_id, stage  (pipeline view)
INDEX:        owner_user_id, deleted_at
INDEX:        client_id  (client's deals)
INDEX:        owner_user_id, created_at DESC  (recency sort)
INDEX:        stage, closed_at  (analytics: closed deals by period)
TRIGGER:      updated_at auto-update
```

**Constraint:** `ai_qualification_score` CHECK (0 <= value <= 100)

### `deal_activity_entries`

```
PRIMARY KEY:  id
INDEX:        deal_id, created_at DESC  (timeline view)
INDEX:        owner_user_id  (tenant audit)
```

---

### `proposals`

```
PRIMARY KEY:  id
UNIQUE:       (deal_id, version_number)
UNIQUE:       share_token WHERE share_token IS NOT NULL
INDEX:        deal_id, status  (active proposals per deal)
INDEX:        owner_user_id, status
INDEX:        owner_user_id, created_at DESC
TRIGGER:      updated_at auto-update
```

**GIN Index:** `content jsonb_path_ops` — enables JSONB path queries on proposal content.

---

### `contracts`

```
PRIMARY KEY:  id
UNIQUE:       (deal_id, version_number)
UNIQUE:       share_token WHERE share_token IS NOT NULL
INDEX:        deal_id, status
INDEX:        owner_user_id, status
INDEX:        client_id
INDEX:        proposal_id
TRIGGER:      updated_at auto-update
```

**Constraint:** Only one row per `deal_id` may have `status IN ('active', 'pending_signatures')` — enforced at application layer with unique partial index:

```sql
CREATE UNIQUE INDEX contracts_one_active_per_deal
  ON contracts (deal_id)
  WHERE status IN ('active', 'pending_signatures');
```

### `contract_payment_milestones`

```
PRIMARY KEY:  id
INDEX:        contract_id, sort_order
INDEX:        invoice_id WHERE invoice_id IS NOT NULL
TRIGGER:      updated_at auto-update
```

---

### `invoices`

```
PRIMARY KEY:  id
UNIQUE:       (owner_user_id, invoice_number)
INDEX:        owner_user_id, status  (status dashboard)
INDEX:        owner_user_id, due_date  (overdue detection job)
INDEX:        client_id
INDEX:        contract_id WHERE contract_id IS NOT NULL
INDEX:        deal_id WHERE deal_id IS NOT NULL
INDEX:        owner_user_id, issue_date DESC  (revenue period queries)
TRIGGER:      updated_at auto-update
```

**Constraints:**
- `CHECK (contract_id IS NOT NULL OR deal_id IS NOT NULL)` — business context required
- `CHECK (amount_paid <= total)` — no overpayment
- `CHECK (total = subtotal + tax_amount)` — arithmetic integrity

### `invoice_line_items`

```
PRIMARY KEY:  id
INDEX:        invoice_id, sort_order
```

**Constraint:** `CHECK (quantity > 0)`, `CHECK (amount = quantity * unit_price)` — enforced at app layer; stored values are source of truth.

### `invoice_payment_records`

```
PRIMARY KEY:  id
INDEX:        invoice_id, payment_date DESC
```

---

### `reminders`

```
PRIMARY KEY:  id
INDEX:        owner_user_id, status, scheduled_at  (worker pickup query)
INDEX:        (target_type, target_id)  (cancel-on-event queries)
INDEX:        parent_reminder_id WHERE parent_reminder_id IS NOT NULL
INDEX:        scheduled_at WHERE status = 'pending'  (scheduler scan)
TRIGGER:      updated_at auto-update
```

**Constraint:** `CHECK (retry_count <= 3)`

**Note:** There is no DB-level FK on `target_id` because it is polymorphic. Referential integrity
is enforced at the application layer.

### `reminder_delivery_records`

```
PRIMARY KEY:  id
INDEX:        reminder_id, attempted_at DESC
```

---

### `revenue_snapshots`

```
PRIMARY KEY:  id
UNIQUE:       (owner_user_id, period_type, period_start)
INDEX:        owner_user_id, period_type, period_start DESC
```

### `pipeline_snapshots`

```
PRIMARY KEY:  id
UNIQUE:       (owner_user_id, stage, snapshot_date)
INDEX:        owner_user_id, snapshot_date DESC
```

---

### `audit_log_entries`

```
PRIMARY KEY:  id
INDEX:        actor_user_id, occurred_at DESC
INDEX:        (target_type, target_id), occurred_at DESC
INDEX:        event_type, occurred_at DESC
```

**Partition strategy (future):** Range-partition by `occurred_at` (monthly) once volume exceeds 10M rows.

### `system_templates`

```
PRIMARY KEY:  id
INDEX:        template_type, is_active
INDEX:        parent_template_id WHERE parent_template_id IS NOT NULL
TRIGGER:      updated_at auto-update
```

### `feature_flags`

```
PRIMARY KEY:  id
UNIQUE:       flag_name
```

**Constraint:** `CHECK (rollout_percentage BETWEEN 0 AND 100)`

### `ai_cost_records`

```
PRIMARY KEY:  id
INDEX:        user_id, occurred_at DESC
INDEX:        ai_module, occurred_at DESC  (admin cost monitoring)
INDEX:        occurred_at DESC  (platform-wide cost rollup)
```

---

## Trigger: `updated_at` Auto-Update

Applied to all tables that carry `updated_at`:

```sql
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```

Applied per table:

```sql
CREATE TRIGGER trg_users_updated_at
  BEFORE UPDATE ON users
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
-- (repeated for every mutable table)
```

---

## Soft-Delete Strategy

| Table | Column | Behavior |
|---|---|---|
| `users` | `deleted_at` | Auth blocks login. All related records retained. |
| `clients` | `deleted_at` | Hidden from list views. Hard-delete blocked if related Deals/Contracts/Invoices exist. |
| `deals` | `deleted_at` | Cascade-cancel pending Reminders via event. |

**Query pattern:** All queries on soft-deletable tables must include `WHERE deleted_at IS NULL`
unless explicitly fetching deleted records (admin use). Partial indexes on `deleted_at` make this efficient.

---

## Multi-Tenant Query Pattern

Every user-facing query on tenant-scoped tables must include `owner_user_id = :current_user_id`.
Never expose rows across users. Example hot path:

```sql
-- Pipeline view
SELECT stage, COUNT(*), COALESCE(SUM(estimated_value), 0)
FROM deals
WHERE owner_user_id = $1
  AND deleted_at IS NULL
GROUP BY stage;
```

The covering index `(owner_user_id, stage)` on `deals` serves this query from the index alone.

---

## Index Summary

| Table | Index | Type | Purpose |
|---|---|---|---|
| users | (email) | UNIQUE BTREE | Login lookup |
| users | (status, deleted_at) | BTREE | Admin user lists |
| oauth_identities | (provider, provider_sub) | UNIQUE BTREE | OAuth login |
| oauth_identities | (user_id) | BTREE | User's identities |
| refresh_tokens | (token_hash) | UNIQUE BTREE | Token validation |
| refresh_tokens | (user_id, expires_at, revoked_at) | BTREE | Active token count |
| token_blacklist | (jti) | UNIQUE BTREE | JWT revocation check |
| token_blacklist | (expires_at) | BTREE | Cleanup job |
| subscriptions | (user_id) | UNIQUE BTREE | One-per-user |
| subscriptions | (plan_id, status) | BTREE | Plan distribution |
| subscriptions | (current_period_end) | BTREE | Renewal job |
| usage_records | (user_id, billing_period_start) | UNIQUE BTREE | Current period lookup |
| billing_events | (user_id, occurred_at DESC) | BTREE | Billing history |
| clients | (owner_user_id, status) | BTREE | Tenant list + filter |
| clients | (owner_user_id, email) PARTIAL WHERE deleted_at IS NULL | UNIQUE BTREE | Email uniqueness |
| clients | (owner_user_id, name) text_pattern_ops | BTREE | Name search |
| deals | (owner_user_id, stage) | BTREE | Pipeline view |
| deals | (client_id) | BTREE | Client's deals |
| deals | (owner_user_id, created_at DESC) | BTREE | Recent deals |
| deals | (stage, closed_at) | BTREE | Analytics |
| proposals | (deal_id, status) | BTREE | Active proposals |
| proposals | (share_token) PARTIAL | UNIQUE BTREE | Client-facing link |
| proposals | (content) | GIN jsonb_path_ops | JSONB search |
| contracts | (deal_id, version_number) | UNIQUE BTREE | Version lookup |
| contracts | (deal_id) PARTIAL WHERE status IN (...) | UNIQUE BTREE | One-active constraint |
| contracts | (owner_user_id, status) | BTREE | Status filter |
| invoices | (owner_user_id, status) | BTREE | Status dashboard |
| invoices | (owner_user_id, due_date) | BTREE | Overdue detection |
| invoices | (owner_user_id, invoice_number) | UNIQUE BTREE | Invoice number |
| invoice_line_items | (invoice_id, sort_order) | BTREE | Ordered line items |
| reminders | (owner_user_id, status, scheduled_at) | BTREE | Worker queue scan |
| reminders | (target_type, target_id) | BTREE | Cancel-on-event |
| reminders | (scheduled_at) PARTIAL WHERE status='pending' | BTREE | Scheduler pickup |
| audit_log_entries | (actor_user_id, occurred_at DESC) | BTREE | User audit trail |
| audit_log_entries | (target_type, target_id, occurred_at DESC) | BTREE | Object history |
| audit_log_entries | (event_type, occurred_at DESC) | BTREE | Event type filter |
| ai_cost_records | (user_id, occurred_at DESC) | BTREE | Per-user cost report |
| ai_cost_records | (occurred_at DESC) | BTREE | Platform cost rollup |
| revenue_snapshots | (owner_user_id, period_type, period_start) | UNIQUE BTREE | Dashboard lookup |
| pipeline_snapshots | (owner_user_id, snapshot_date DESC) | BTREE | Trend queries |
