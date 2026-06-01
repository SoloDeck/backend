# Logical ERD — SoloDesk

All tables use UUID primary keys and carry `created_at` / `updated_at` audit timestamps unless
noted as append-only (those carry only `created_at`).

---

## Domain: Identity & Access

### `users`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `email` | VARCHAR(255) | NOT NULL, UNIQUE | Globally unique |
| `full_name` | VARCHAR(255) | NOT NULL | |
| `role` | ENUM(freelancer, admin) | NOT NULL, DEFAULT freelancer | |
| `status` | ENUM(active, suspended, deleted) | NOT NULL, DEFAULT active | |
| `avatar_url` | TEXT | NULL | Object storage URL |
| `bio` | TEXT | NULL | |
| `phone` | VARCHAR(50) | NULL | |
| `skills` | TEXT[] | NULL | Professional profile |
| `specialization` | VARCHAR(255) | NULL | Professional profile |
| `default_hourly_rate` | NUMERIC(12,2) | NULL | Professional profile |
| `currency` | CHAR(3) | NOT NULL, DEFAULT 'VND' | ISO 4217 |
| `portfolio_url` | TEXT | NULL | Professional profile |
| `business_name` | VARCHAR(255) | NULL | Professional profile |
| `locale` | CHAR(5) | NOT NULL, DEFAULT 'vi' | BCP 47 |
| `timezone` | VARCHAR(100) | NOT NULL, DEFAULT 'Asia/Ho_Chi_Minh' | IANA tz |
| `notification_channel` | ENUM(email, in_app, both) | NOT NULL, DEFAULT both | Preferences |
| `theme` | ENUM(light, dark) | NOT NULL, DEFAULT light | Preferences |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | |
| `deleted_at` | TIMESTAMPTZ | NULL | Soft delete |

### `oauth_identities`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `user_id` | UUID | FK → users.id, NOT NULL | |
| `provider` | VARCHAR(50) | NOT NULL | e.g. 'google' |
| `provider_sub` | VARCHAR(255) | NOT NULL | Google sub claim |
| `provider_email` | VARCHAR(255) | NULL | Email from provider |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Append-only |

**Unique:** (`provider`, `provider_sub`)

### `refresh_tokens`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `user_id` | UUID | FK → users.id, NOT NULL | |
| `token_hash` | VARCHAR(255) | NOT NULL, UNIQUE | SHA-256 of opaque token |
| `device_hint` | VARCHAR(255) | NULL | User-agent or device label |
| `expires_at` | TIMESTAMPTZ | NOT NULL | |
| `revoked_at` | TIMESTAMPTZ | NULL | NULL = still valid |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | |

### `password_reset_tokens`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `user_id` | UUID | FK → users.id, NOT NULL | |
| `token_hash` | VARCHAR(255) | NOT NULL, UNIQUE | SHA-256 of email token |
| `expires_at` | TIMESTAMPTZ | NOT NULL | +1 hour from creation |
| `used_at` | TIMESTAMPTZ | NULL | Single-use; set on redemption |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | |

### `token_blacklist`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `jti` | VARCHAR(255) | NOT NULL, UNIQUE | JWT ID claim |
| `user_id` | UUID | FK → users.id, NOT NULL | |
| `expires_at` | TIMESTAMPTZ | NOT NULL | Matches JWT expiry |
| `blacklisted_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Append-only |

---

## Domain: Subscriptions

### `subscription_plans`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `name` | VARCHAR(100) | NOT NULL, UNIQUE | Free, Pro, Agency |
| `slug` | VARCHAR(50) | NOT NULL, UNIQUE | free, pro, agency |
| `price_monthly` | NUMERIC(10,2) | NOT NULL, DEFAULT 0 | |
| `currency` | CHAR(3) | NOT NULL, DEFAULT 'USD' | |
| `max_ai_generations_per_month` | INT | NOT NULL, DEFAULT 0 | 0 = none |
| `can_use_ai` | BOOLEAN | NOT NULL, DEFAULT FALSE | |
| `can_export_pdf` | BOOLEAN | NOT NULL, DEFAULT FALSE | |
| `max_clients` | INT | NULL | NULL = unlimited |
| `max_deals` | INT | NULL | NULL = unlimited |
| `is_active` | BOOLEAN | NOT NULL, DEFAULT TRUE | |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | |

### `subscriptions`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `user_id` | UUID | FK → users.id, NOT NULL, UNIQUE | One per user |
| `plan_id` | UUID | FK → subscription_plans.id, NOT NULL | |
| `status` | ENUM(active, past_due, suspended, cancelled) | NOT NULL, DEFAULT active | |
| `current_period_start` | TIMESTAMPTZ | NOT NULL | |
| `current_period_end` | TIMESTAMPTZ | NOT NULL | |
| `cancel_at_period_end` | BOOLEAN | NOT NULL, DEFAULT FALSE | |
| `cancelled_at` | TIMESTAMPTZ | NULL | |
| `stripe_subscription_id` | VARCHAR(255) | NULL, UNIQUE | External billing ref |
| `stripe_customer_id` | VARCHAR(255) | NULL | External billing ref |
| `override_by_admin_id` | UUID | FK → users.id, NULL | Admin override actor |
| `override_expires_at` | TIMESTAMPTZ | NULL | Admin override expiry |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | |

### `usage_records`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `user_id` | UUID | FK → users.id, NOT NULL | |
| `subscription_id` | UUID | FK → subscriptions.id, NOT NULL | |
| `billing_period_start` | TIMESTAMPTZ | NOT NULL | |
| `billing_period_end` | TIMESTAMPTZ | NOT NULL | |
| `ai_generations_used` | INT | NOT NULL, DEFAULT 0 | |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | |

**Unique:** (`user_id`, `billing_period_start`)

### `billing_events`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `user_id` | UUID | FK → users.id, NOT NULL | |
| `subscription_id` | UUID | FK → subscriptions.id, NOT NULL | |
| `event_type` | ENUM(payment_succeeded, payment_failed, subscription_renewed, subscription_cancelled) | NOT NULL | |
| `amount` | NUMERIC(10,2) | NULL | |
| `currency` | CHAR(3) | NULL | |
| `stripe_event_id` | VARCHAR(255) | NULL, UNIQUE | Idempotency key |
| `metadata` | JSONB | NULL | Raw provider payload |
| `occurred_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Append-only |

---

## Domain: Clients

### `clients`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `owner_user_id` | UUID | FK → users.id, NOT NULL | Tenant scope |
| `type` | ENUM(individual, company) | NOT NULL, DEFAULT individual | |
| `name` | VARCHAR(255) | NOT NULL | |
| `email` | VARCHAR(255) | NULL | |
| `phone` | VARCHAR(50) | NULL | |
| `website` | TEXT | NULL | |
| `linkedin_url` | TEXT | NULL | |
| `address_city` | VARCHAR(100) | NULL | |
| `address_country` | VARCHAR(100) | NULL | |
| `status` | ENUM(prospect, active, inactive, archived) | NOT NULL, DEFAULT prospect | |
| `notes` | TEXT | NULL | |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | |
| `deleted_at` | TIMESTAMPTZ | NULL | Soft delete |

**Unique:** (`owner_user_id`, `email`) WHERE `deleted_at IS NULL`

### `client_tags`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `client_id` | UUID | FK → clients.id, NOT NULL | |
| `tag` | VARCHAR(100) | NOT NULL | Stored lowercase |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Append-only |

**Unique:** (`client_id`, `tag`)

### `client_communication_logs`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `client_id` | UUID | FK → clients.id, NOT NULL | |
| `owner_user_id` | UUID | FK → users.id, NOT NULL | Denormalized for tenant filter |
| `channel` | ENUM(email, phone, meeting, message) | NOT NULL | |
| `summary` | TEXT | NOT NULL | |
| `communicated_at` | TIMESTAMPTZ | NOT NULL | When touchpoint occurred |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Append-only |

---

## Domain: Deals

### `deals`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `owner_user_id` | UUID | FK → users.id, NOT NULL | Tenant scope |
| `client_id` | UUID | FK → clients.id, NOT NULL | Immutable after creation |
| `title` | VARCHAR(500) | NOT NULL | |
| `stage` | ENUM(new_lead, qualified, proposal_sent, in_negotiation, active, completed_and_billed, lost) | NOT NULL, DEFAULT new_lead | |
| `source` | ENUM(inbound, referral, outreach, platform, other) | NULL | |
| `estimated_value` | NUMERIC(15,2) | NULL | |
| `actual_value` | NUMERIC(15,2) | NULL | Set at terminal stage |
| `currency` | CHAR(3) | NOT NULL, DEFAULT 'VND' | |
| `notes` | TEXT | NULL | |
| `ai_qualification_score` | SMALLINT | NULL, CHECK 0–100 | From AI domain |
| `ai_qualification_recommendation` | ENUM(qualify, pass) | NULL | From AI domain |
| `closed_at` | TIMESTAMPTZ | NULL | Set when terminal |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | |
| `deleted_at` | TIMESTAMPTZ | NULL | Soft delete |

### `deal_activity_entries`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `deal_id` | UUID | FK → deals.id, NOT NULL | |
| `owner_user_id` | UUID | FK → users.id, NOT NULL | Denormalized for tenant filter |
| `entry_type` | ENUM(stage_change, note_added, document_attached, ai_qualification) | NOT NULL | |
| `description` | TEXT | NOT NULL | |
| `previous_stage` | ENUM(deal_stage) | NULL | Populated on stage_change |
| `new_stage` | ENUM(deal_stage) | NULL | Populated on stage_change |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Append-only |

---

## Domain: Proposals

### `proposals`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `deal_id` | UUID | FK → deals.id, NOT NULL | Immutable after creation |
| `owner_user_id` | UUID | FK → users.id, NOT NULL | Tenant scope |
| `version_number` | INT | NOT NULL, DEFAULT 1 | Increments per deal |
| `status` | ENUM(draft, sent, accepted, rejected, expired, superseded) | NOT NULL, DEFAULT draft | |
| `content` | JSONB | NOT NULL, DEFAULT '{}' | Full proposal structure |
| `share_token` | VARCHAR(255) | NULL, UNIQUE | Client-facing access token |
| `share_expires_at` | TIMESTAMPTZ | NULL | |
| `sent_at` | TIMESTAMPTZ | NULL | |
| `responded_at` | TIMESTAMPTZ | NULL | Client accept/reject time |
| `ai_generated` | BOOLEAN | NOT NULL, DEFAULT FALSE | |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | |

**Unique:** (`deal_id`, `version_number`)

**JSONB `content` structure:**
```json
{
  "title": "string",
  "executive_summary": "string",
  "scope_of_work": "string",
  "timeline": { "start_date": "date", "end_date": "date", "milestones": [] },
  "pricing": { "line_items": [], "total": 0, "currency": "VND" },
  "terms": { "payment_terms": "string", "revision_policy": "string", "ip_ownership": "string" },
  "notes": "string"
}
```

---

## Domain: Contracts

### `contracts`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `deal_id` | UUID | FK → deals.id, NOT NULL | Immutable |
| `proposal_id` | UUID | FK → proposals.id, NOT NULL | Immutable |
| `client_id` | UUID | FK → clients.id, NOT NULL | For indexed queries |
| `owner_user_id` | UUID | FK → users.id, NOT NULL | Tenant scope |
| `version_number` | INT | NOT NULL, DEFAULT 1 | Increments on amendment |
| `status` | ENUM(draft, pending_signatures, active, completed, terminated, expired) | NOT NULL, DEFAULT draft | |
| `content` | JSONB | NOT NULL, DEFAULT '{}' | Full contract structure |
| `client_snapshot` | JSONB | NOT NULL, DEFAULT '{}' | Client data at creation time |
| `signed_by_freelancer_at` | TIMESTAMPTZ | NULL | |
| `signed_by_client_at` | TIMESTAMPTZ | NULL | |
| `effective_date` | DATE | NULL | |
| `end_date` | DATE | NULL | |
| `share_token` | VARCHAR(255) | NULL, UNIQUE | Client-facing access token |
| `share_expires_at` | TIMESTAMPTZ | NULL | |
| `parent_contract_id` | UUID | FK → contracts.id, NULL | Previous version on amendment |
| `ai_generated` | BOOLEAN | NOT NULL, DEFAULT FALSE | |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | |

**Unique:** (`deal_id`, `version_number`)

### `contract_payment_milestones`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `contract_id` | UUID | FK → contracts.id, NOT NULL | |
| `description` | TEXT | NOT NULL | |
| `amount` | NUMERIC(15,2) | NOT NULL, CHECK > 0 | |
| `due_date` | DATE | NULL | |
| `invoice_id` | UUID | FK → invoices.id, NULL | Linked when invoice issued |
| `sort_order` | SMALLINT | NOT NULL, DEFAULT 0 | Display ordering |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | |

---

## Domain: Invoices

### `invoices`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `owner_user_id` | UUID | FK → users.id, NOT NULL | Tenant scope |
| `client_id` | UUID | FK → clients.id, NOT NULL | For queries |
| `contract_id` | UUID | FK → contracts.id, NULL | |
| `deal_id` | UUID | FK → deals.id, NULL | |
| `invoice_number` | VARCHAR(100) | NOT NULL | User-scoped sequential |
| `status` | ENUM(draft, sent, partially_paid, paid, overdue, void) | NOT NULL, DEFAULT draft | |
| `issue_date` | DATE | NOT NULL | |
| `due_date` | DATE | NOT NULL | |
| `currency` | CHAR(3) | NOT NULL, DEFAULT 'VND' | |
| `subtotal` | NUMERIC(15,2) | NOT NULL, DEFAULT 0 | Sum of line items |
| `tax_rate` | NUMERIC(5,4) | NOT NULL, DEFAULT 0 | e.g. 0.1 = 10% |
| `tax_amount` | NUMERIC(15,2) | NOT NULL, DEFAULT 0 | |
| `total` | NUMERIC(15,2) | NOT NULL, DEFAULT 0 | subtotal + tax_amount |
| `amount_paid` | NUMERIC(15,2) | NOT NULL, DEFAULT 0 | Running sum of payments |
| `notes` | TEXT | NULL | |
| `client_snapshot` | JSONB | NOT NULL, DEFAULT '{}' | Client data at creation time |
| `sent_at` | TIMESTAMPTZ | NULL | |
| `voided_at` | TIMESTAMPTZ | NULL | |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | |

**Unique:** (`owner_user_id`, `invoice_number`)

**Check:** `contract_id IS NOT NULL OR deal_id IS NOT NULL`

**Check:** `amount_paid <= total`

**Check:** `total = subtotal + tax_amount`

### `invoice_line_items`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `invoice_id` | UUID | FK → invoices.id, NOT NULL | |
| `description` | TEXT | NOT NULL | |
| `quantity` | NUMERIC(10,4) | NOT NULL, DEFAULT 1, CHECK > 0 | |
| `unit_price` | NUMERIC(15,2) | NOT NULL | |
| `amount` | NUMERIC(15,2) | NOT NULL | quantity × unit_price |
| `sort_order` | SMALLINT | NOT NULL, DEFAULT 0 | |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Append-only |

### `invoice_payment_records`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `invoice_id` | UUID | FK → invoices.id, NOT NULL | |
| `amount` | NUMERIC(15,2) | NOT NULL, CHECK > 0 | |
| `payment_date` | DATE | NOT NULL | |
| `payment_method` | ENUM(bank_transfer, cash, online, other) | NOT NULL, DEFAULT other | |
| `reference_note` | TEXT | NULL | |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Append-only |

---

## Domain: Reminders

### `reminders`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `owner_user_id` | UUID | FK → users.id, NOT NULL | Tenant scope |
| `target_type` | ENUM(deal, client, invoice, contract) | NOT NULL | Polymorphic FK type |
| `target_id` | UUID | NOT NULL | Polymorphic FK value |
| `reminder_type` | ENUM(follow_up, proposal_follow_up, contract_signing_nudge, payment_due, payment_overdue, re_engagement, custom) | NOT NULL | |
| `channel` | ENUM(email, in_app, both) | NOT NULL, DEFAULT both | |
| `status` | ENUM(pending, sent, failed, cancelled, skipped) | NOT NULL, DEFAULT pending | |
| `scheduled_at` | TIMESTAMPTZ | NOT NULL | Must be in the future at creation |
| `message_preview` | TEXT | NULL | Editable before first send |
| `recurrence_rule` | TEXT | NULL | RRULE string |
| `parent_reminder_id` | UUID | FK → reminders.id, NULL | Head of recurring series |
| `retry_count` | SMALLINT | NOT NULL, DEFAULT 0 | Max 3 retries |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | |

### `reminder_delivery_records`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `reminder_id` | UUID | FK → reminders.id, NOT NULL | |
| `attempted_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | |
| `channel` | ENUM(email, in_app, both) | NOT NULL | |
| `outcome` | ENUM(success, failure) | NOT NULL | |
| `error_message` | TEXT | NULL | |

---

## Domain: Analytics (Derived / Read-Optimized)

### `revenue_snapshots`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `owner_user_id` | UUID | FK → users.id, NOT NULL | |
| `period_type` | ENUM(monthly, quarterly, yearly) | NOT NULL | |
| `period_start` | DATE | NOT NULL | |
| `period_end` | DATE | NOT NULL | |
| `total_invoiced` | NUMERIC(15,2) | NOT NULL, DEFAULT 0 | |
| `total_collected` | NUMERIC(15,2) | NOT NULL, DEFAULT 0 | |
| `total_outstanding` | NUMERIC(15,2) | NOT NULL, DEFAULT 0 | |
| `total_overdue` | NUMERIC(15,2) | NOT NULL, DEFAULT 0 | |
| `computed_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Last refresh time |

**Unique:** (`owner_user_id`, `period_type`, `period_start`)

### `pipeline_snapshots`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `owner_user_id` | UUID | FK → users.id, NOT NULL | |
| `stage` | ENUM(deal_stage) | NOT NULL | |
| `deal_count` | INT | NOT NULL, DEFAULT 0 | |
| `total_value` | NUMERIC(15,2) | NOT NULL, DEFAULT 0 | |
| `snapshot_date` | DATE | NOT NULL | |
| `computed_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | |

**Unique:** (`owner_user_id`, `stage`, `snapshot_date`)

---

## Domain: Admin

### `audit_log_entries`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `event_type` | VARCHAR(100) | NOT NULL | Namespaced: `auth.user_logged_in` |
| `actor_user_id` | UUID | FK → users.id, NULL | NULL = system event |
| `target_type` | VARCHAR(100) | NULL | e.g. `user`, `deal` |
| `target_id` | UUID | NULL | |
| `description` | TEXT | NOT NULL | Human-readable summary |
| `ip_address` | INET | NULL | |
| `metadata` | JSONB | NULL | Extra structured context |
| `occurred_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Append-only; never modified |

### `system_templates`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `template_type` | ENUM(proposal, contract) | NOT NULL | |
| `name` | VARCHAR(255) | NOT NULL | |
| `content` | JSONB | NOT NULL | Template body |
| `plan_tier_required` | VARCHAR(50) | NULL | NULL = all plans |
| `version_number` | INT | NOT NULL, DEFAULT 1 | |
| `is_active` | BOOLEAN | NOT NULL, DEFAULT FALSE | |
| `parent_template_id` | UUID | FK → system_templates.id, NULL | Previous version |
| `created_by_admin_id` | UUID | FK → users.id, NOT NULL | |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | |

### `feature_flags`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `flag_name` | VARCHAR(100) | NOT NULL, UNIQUE | |
| `is_enabled` | BOOLEAN | NOT NULL, DEFAULT FALSE | |
| `rollout_percentage` | SMALLINT | NOT NULL, DEFAULT 0, CHECK 0–100 | |
| `target_user_ids` | UUID[] | NULL | Explicit user allowlist |
| `description` | TEXT | NULL | |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | |

### `ai_cost_records`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `user_id` | UUID | FK → users.id, NOT NULL | |
| `ai_module` | ENUM(lead_qualifier, proposal_generator, contract_generator, followup_generator) | NOT NULL | |
| `model_used` | VARCHAR(100) | NOT NULL | e.g. 'gpt-4o' |
| `input_tokens` | INT | NOT NULL, DEFAULT 0 | |
| `output_tokens` | INT | NOT NULL, DEFAULT 0 | |
| `estimated_cost_usd` | NUMERIC(10,6) | NOT NULL, DEFAULT 0 | |
| `status` | ENUM(pending, completed, failed) | NOT NULL, DEFAULT completed | |
| `input_hash` | CHAR(64) | NULL | SHA-256 for deduplication |
| `occurred_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Append-only |

---

## Relationship Matrix

| Entity A | Cardinality | Entity B | FK Location | Notes |
|---|---|---|---|---|
| users | 1 : 0..1 | subscriptions | subscriptions.user_id | UNIQUE |
| subscription_plans | 1 : 0..N | subscriptions | subscriptions.plan_id | |
| subscriptions | 1 : 0..N | usage_records | usage_records.subscription_id | |
| subscriptions | 1 : 0..N | billing_events | billing_events.subscription_id | |
| users | 1 : 0..N | oauth_identities | oauth_identities.user_id | |
| users | 1 : 0..N | refresh_tokens | refresh_tokens.user_id | |
| users | 1 : 0..N | clients | clients.owner_user_id | |
| clients | 1 : 0..N | client_tags | client_tags.client_id | |
| clients | 1 : 0..N | client_communication_logs | client_communication_logs.client_id | |
| clients | 1 : 0..N | deals | deals.client_id | client_id immutable |
| deals | 1 : 0..N | proposals | proposals.deal_id | deal_id immutable |
| deals | 1 : 0..N | deal_activity_entries | deal_activity_entries.deal_id | |
| deals | 1 : 0..N | contracts | contracts.deal_id | deal_id immutable |
| deals | 1 : 0..N | invoices | invoices.deal_id | |
| proposals | 1 : 0..1 | contracts | contracts.proposal_id | proposal_id immutable |
| contracts | 1 : 1..N | contract_payment_milestones | contract_payment_milestones.contract_id | |
| contracts | 1 : 0..N | invoices | invoices.contract_id | |
| contract_payment_milestones | 0..1 : 0..1 | invoices | contract_payment_milestones.invoice_id | |
| invoices | 1 : 1..N | invoice_line_items | invoice_line_items.invoice_id | |
| invoices | 1 : 0..N | invoice_payment_records | invoice_payment_records.invoice_id | |
| users | 1 : 0..N | reminders | reminders.owner_user_id | |
| reminders | 1 : 0..N | reminder_delivery_records | reminder_delivery_records.reminder_id | |
| reminders | 0..1 : 0..N | reminders | reminders.parent_reminder_id | Recurring series |
| users | 1 : 0..N | revenue_snapshots | revenue_snapshots.owner_user_id | |
| users | 1 : 0..N | pipeline_snapshots | pipeline_snapshots.owner_user_id | |
| users | 1 : 0..N | ai_cost_records | ai_cost_records.user_id | |
| contracts | 0..1 : 0..1 | contracts | contracts.parent_contract_id | Amendment chain |
| system_templates | 0..1 : 0..N | system_templates | system_templates.parent_template_id | Version chain |
