-- =============================================================================
-- SoloDesk Database Schema
-- PostgreSQL 15+
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Extensions
-- ---------------------------------------------------------------------------

CREATE EXTENSION IF NOT EXISTS "pgcrypto";  -- gen_random_uuid()


-- ---------------------------------------------------------------------------
-- Enums
-- ---------------------------------------------------------------------------

CREATE TYPE user_role            AS ENUM ('freelancer', 'admin');
CREATE TYPE user_status          AS ENUM ('active', 'suspended', 'deleted');
CREATE TYPE notification_channel AS ENUM ('email', 'in_app', 'both');
CREATE TYPE theme_preference     AS ENUM ('light', 'dark');

CREATE TYPE subscription_status  AS ENUM ('active', 'past_due', 'suspended', 'cancelled');
CREATE TYPE billing_event_type   AS ENUM (
    'payment_succeeded',
    'payment_failed',
    'subscription_renewed',
    'subscription_cancelled'
);

CREATE TYPE client_type          AS ENUM ('individual', 'company');
CREATE TYPE client_status        AS ENUM ('prospect', 'active', 'inactive', 'archived');
CREATE TYPE comm_channel         AS ENUM ('email', 'phone', 'meeting', 'message');

CREATE TYPE deal_stage           AS ENUM (
    'new_lead',
    'qualified',
    'proposal_sent',
    'in_negotiation',
    'active',
    'completed_and_billed',
    'lost'
);
CREATE TYPE deal_source          AS ENUM ('inbound', 'referral', 'outreach', 'platform', 'other');
CREATE TYPE deal_activity_type   AS ENUM (
    'stage_change',
    'note_added',
    'document_attached',
    'ai_qualification'
);
CREATE TYPE ai_recommendation    AS ENUM ('qualify', 'pass');

CREATE TYPE proposal_status      AS ENUM (
    'draft',
    'sent',
    'accepted',
    'rejected',
    'expired',
    'superseded'
);

CREATE TYPE contract_status      AS ENUM (
    'draft',
    'pending_signatures',
    'active',
    'completed',
    'terminated',
    'expired'
);

CREATE TYPE invoice_status       AS ENUM (
    'draft',
    'sent',
    'partially_paid',
    'paid',
    'overdue',
    'void'
);
CREATE TYPE payment_method       AS ENUM ('bank_transfer', 'cash', 'online', 'other');

CREATE TYPE reminder_target_type AS ENUM ('deal', 'client', 'invoice', 'contract');
CREATE TYPE reminder_type_enum   AS ENUM (
    'follow_up',
    'proposal_follow_up',
    'contract_signing_nudge',
    'payment_due',
    'payment_overdue',
    're_engagement',
    'custom'
);
CREATE TYPE reminder_status      AS ENUM ('pending', 'sent', 'failed', 'cancelled', 'skipped');
CREATE TYPE reminder_outcome     AS ENUM ('success', 'failure');

CREATE TYPE template_type        AS ENUM ('proposal', 'contract');

CREATE TYPE ai_module_type       AS ENUM (
    'lead_qualifier',
    'proposal_generator',
    'contract_generator',
    'followup_generator'
);
CREATE TYPE ai_generation_status AS ENUM ('pending', 'completed', 'failed');

CREATE TYPE period_type          AS ENUM ('monthly', 'quarterly', 'yearly');


-- ---------------------------------------------------------------------------
-- updated_at trigger function
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- =============================================================================
-- DOMAIN: Identity & Access
-- =============================================================================

CREATE TABLE users (
    id                      UUID            NOT NULL DEFAULT gen_random_uuid(),
    email                   VARCHAR(255)    NOT NULL,
    full_name               VARCHAR(255)    NOT NULL,
    role                    user_role       NOT NULL DEFAULT 'freelancer',
    status                  user_status     NOT NULL DEFAULT 'active',
    hashed_password         VARCHAR(255),           -- NULL for OAuth-only accounts
    avatar_url              TEXT,
    bio                     TEXT,
    phone                   VARCHAR(50),

    -- Professional profile (embedded value object)
    skills                  TEXT[],
    specialization          VARCHAR(255),
    default_hourly_rate     NUMERIC(12,2),
    currency                CHAR(3)         NOT NULL DEFAULT 'VND',
    portfolio_url           TEXT,
    business_name           VARCHAR(255),

    -- Preferences (embedded value object)
    locale                  CHAR(5)         NOT NULL DEFAULT 'vi',
    timezone                VARCHAR(100)    NOT NULL DEFAULT 'Asia/Ho_Chi_Minh',
    notification_channel    notification_channel NOT NULL DEFAULT 'both',
    theme                   theme_preference     NOT NULL DEFAULT 'light',

    -- Audit
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    deleted_at              TIMESTAMPTZ,

    CONSTRAINT pk_users PRIMARY KEY (id),
    CONSTRAINT uq_users_email UNIQUE (email)
);

CREATE INDEX idx_users_status_deleted ON users (status, deleted_at);

CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------

CREATE TABLE oauth_identities (
    id              UUID            NOT NULL DEFAULT gen_random_uuid(),
    user_id         UUID            NOT NULL,
    provider        VARCHAR(50)     NOT NULL,
    provider_sub    VARCHAR(255)    NOT NULL,
    provider_email  VARCHAR(255),
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_oauth_identities PRIMARY KEY (id),
    CONSTRAINT fk_oauth_identities_user FOREIGN KEY (user_id) REFERENCES users (id),
    CONSTRAINT uq_oauth_identities_provider_sub UNIQUE (provider, provider_sub)
);

CREATE INDEX idx_oauth_identities_user_id ON oauth_identities (user_id);

-- ---------------------------------------------------------------------------

CREATE TABLE refresh_tokens (
    id          UUID            NOT NULL DEFAULT gen_random_uuid(),
    user_id     UUID            NOT NULL,
    token_hash  VARCHAR(255)    NOT NULL,
    device_hint VARCHAR(255),
    expires_at  TIMESTAMPTZ     NOT NULL,
    revoked_at  TIMESTAMPTZ,
    created_at  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_refresh_tokens PRIMARY KEY (id),
    CONSTRAINT fk_refresh_tokens_user FOREIGN KEY (user_id) REFERENCES users (id),
    CONSTRAINT uq_refresh_tokens_hash UNIQUE (token_hash)
);

CREATE INDEX idx_refresh_tokens_user_validity
    ON refresh_tokens (user_id, expires_at, revoked_at);

-- ---------------------------------------------------------------------------

CREATE TABLE password_reset_tokens (
    id          UUID            NOT NULL DEFAULT gen_random_uuid(),
    user_id     UUID            NOT NULL,
    token_hash  VARCHAR(255)    NOT NULL,
    expires_at  TIMESTAMPTZ     NOT NULL,
    used_at     TIMESTAMPTZ,
    created_at  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_password_reset_tokens PRIMARY KEY (id),
    CONSTRAINT fk_password_reset_tokens_user FOREIGN KEY (user_id) REFERENCES users (id),
    CONSTRAINT uq_password_reset_tokens_hash UNIQUE (token_hash)
);

CREATE INDEX idx_password_reset_tokens_user ON password_reset_tokens (user_id, expires_at);

-- ---------------------------------------------------------------------------

CREATE TABLE token_blacklist (
    id              UUID            NOT NULL DEFAULT gen_random_uuid(),
    jti             VARCHAR(255)    NOT NULL,
    user_id         UUID            NOT NULL,
    expires_at      TIMESTAMPTZ     NOT NULL,
    blacklisted_at  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_token_blacklist PRIMARY KEY (id),
    CONSTRAINT fk_token_blacklist_user FOREIGN KEY (user_id) REFERENCES users (id),
    CONSTRAINT uq_token_blacklist_jti UNIQUE (jti)
);

CREATE INDEX idx_token_blacklist_expires ON token_blacklist (expires_at);


-- =============================================================================
-- DOMAIN: Subscriptions
-- =============================================================================

CREATE TABLE subscription_plans (
    id                              UUID            NOT NULL DEFAULT gen_random_uuid(),
    name                            VARCHAR(100)    NOT NULL,
    slug                            VARCHAR(50)     NOT NULL,
    price_monthly                   NUMERIC(10,2)   NOT NULL DEFAULT 0,
    currency                        CHAR(3)         NOT NULL DEFAULT 'USD',
    max_ai_generations_per_month    INT             NOT NULL DEFAULT 0,
    can_use_ai                      BOOLEAN         NOT NULL DEFAULT FALSE,
    can_export_pdf                  BOOLEAN         NOT NULL DEFAULT FALSE,
    max_clients                     INT,
    max_deals                       INT,
    is_active                       BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at                      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at                      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_subscription_plans PRIMARY KEY (id),
    CONSTRAINT uq_subscription_plans_name UNIQUE (name),
    CONSTRAINT uq_subscription_plans_slug UNIQUE (slug),
    CONSTRAINT chk_subscription_plans_price CHECK (price_monthly >= 0)
);

CREATE INDEX idx_subscription_plans_active ON subscription_plans (is_active);

CREATE TRIGGER trg_subscription_plans_updated_at
    BEFORE UPDATE ON subscription_plans
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------

CREATE TABLE subscriptions (
    id                      UUID                NOT NULL DEFAULT gen_random_uuid(),
    user_id                 UUID                NOT NULL,
    plan_id                 UUID                NOT NULL,
    status                  subscription_status NOT NULL DEFAULT 'active',
    current_period_start    TIMESTAMPTZ         NOT NULL,
    current_period_end      TIMESTAMPTZ         NOT NULL,
    cancel_at_period_end    BOOLEAN             NOT NULL DEFAULT FALSE,
    cancelled_at            TIMESTAMPTZ,
    stripe_subscription_id  VARCHAR(255),
    stripe_customer_id      VARCHAR(255),
    override_by_admin_id    UUID,
    override_expires_at     TIMESTAMPTZ,
    created_at              TIMESTAMPTZ         NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ         NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_subscriptions PRIMARY KEY (id),
    CONSTRAINT fk_subscriptions_user FOREIGN KEY (user_id) REFERENCES users (id),
    CONSTRAINT fk_subscriptions_plan FOREIGN KEY (plan_id) REFERENCES subscription_plans (id),
    CONSTRAINT fk_subscriptions_admin FOREIGN KEY (override_by_admin_id) REFERENCES users (id),
    CONSTRAINT uq_subscriptions_user UNIQUE (user_id),
    CONSTRAINT uq_subscriptions_stripe UNIQUE (stripe_subscription_id)
);

CREATE INDEX idx_subscriptions_plan_status ON subscriptions (plan_id, status);
CREATE INDEX idx_subscriptions_period_end  ON subscriptions (current_period_end);

CREATE TRIGGER trg_subscriptions_updated_at
    BEFORE UPDATE ON subscriptions
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------

CREATE TABLE usage_records (
    id                      UUID        NOT NULL DEFAULT gen_random_uuid(),
    user_id                 UUID        NOT NULL,
    subscription_id         UUID        NOT NULL,
    billing_period_start    TIMESTAMPTZ NOT NULL,
    billing_period_end      TIMESTAMPTZ NOT NULL,
    ai_generations_used     INT         NOT NULL DEFAULT 0,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_usage_records PRIMARY KEY (id),
    CONSTRAINT fk_usage_records_user         FOREIGN KEY (user_id)         REFERENCES users (id),
    CONSTRAINT fk_usage_records_subscription FOREIGN KEY (subscription_id) REFERENCES subscriptions (id),
    CONSTRAINT uq_usage_records_user_period  UNIQUE (user_id, billing_period_start),
    CONSTRAINT chk_usage_records_count CHECK (ai_generations_used >= 0)
);

CREATE INDEX idx_usage_records_subscription ON usage_records (subscription_id);

CREATE TRIGGER trg_usage_records_updated_at
    BEFORE UPDATE ON usage_records
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------

CREATE TABLE billing_events (
    id              UUID                NOT NULL DEFAULT gen_random_uuid(),
    user_id         UUID                NOT NULL,
    subscription_id UUID                NOT NULL,
    event_type      billing_event_type  NOT NULL,
    amount          NUMERIC(10,2),
    currency        CHAR(3),
    stripe_event_id VARCHAR(255),
    metadata        JSONB,
    occurred_at     TIMESTAMPTZ         NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_billing_events PRIMARY KEY (id),
    CONSTRAINT fk_billing_events_user         FOREIGN KEY (user_id)         REFERENCES users (id),
    CONSTRAINT fk_billing_events_subscription FOREIGN KEY (subscription_id) REFERENCES subscriptions (id),
    CONSTRAINT uq_billing_events_stripe       UNIQUE (stripe_event_id)
);

CREATE INDEX idx_billing_events_user ON billing_events (user_id, occurred_at DESC);
CREATE INDEX idx_billing_events_subscription ON billing_events (subscription_id);


-- =============================================================================
-- DOMAIN: Clients
-- =============================================================================

CREATE TABLE clients (
    id              UUID            NOT NULL DEFAULT gen_random_uuid(),
    owner_user_id   UUID            NOT NULL,
    type            client_type     NOT NULL DEFAULT 'individual',
    name            VARCHAR(255)    NOT NULL,
    email           VARCHAR(255),
    phone           VARCHAR(50),
    website         TEXT,
    linkedin_url    TEXT,
    address_city    VARCHAR(100),
    address_country VARCHAR(100),
    status          client_status   NOT NULL DEFAULT 'prospect',
    notes           TEXT,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ,

    CONSTRAINT pk_clients PRIMARY KEY (id),
    CONSTRAINT fk_clients_user FOREIGN KEY (owner_user_id) REFERENCES users (id)
);

CREATE UNIQUE INDEX uq_clients_owner_email
    ON clients (owner_user_id, email)
    WHERE deleted_at IS NULL;

CREATE INDEX idx_clients_owner_status  ON clients (owner_user_id, status);
CREATE INDEX idx_clients_owner_deleted ON clients (owner_user_id, deleted_at);
CREATE INDEX idx_clients_owner_name    ON clients (owner_user_id, name text_pattern_ops);

CREATE TRIGGER trg_clients_updated_at
    BEFORE UPDATE ON clients
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------

CREATE TABLE client_tags (
    id          UUID        NOT NULL DEFAULT gen_random_uuid(),
    client_id   UUID        NOT NULL,
    tag         VARCHAR(100) NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_client_tags PRIMARY KEY (id),
    CONSTRAINT fk_client_tags_client FOREIGN KEY (client_id) REFERENCES clients (id),
    CONSTRAINT uq_client_tags_tag UNIQUE (client_id, tag)
);

CREATE INDEX idx_client_tags_client ON client_tags (client_id);

-- ---------------------------------------------------------------------------

CREATE TABLE client_communication_logs (
    id              UUID            NOT NULL DEFAULT gen_random_uuid(),
    client_id       UUID            NOT NULL,
    owner_user_id   UUID            NOT NULL,
    channel         comm_channel    NOT NULL,
    summary         TEXT            NOT NULL,
    communicated_at TIMESTAMPTZ     NOT NULL,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_client_communication_logs PRIMARY KEY (id),
    CONSTRAINT fk_client_comm_logs_client FOREIGN KEY (client_id)     REFERENCES clients (id),
    CONSTRAINT fk_client_comm_logs_user   FOREIGN KEY (owner_user_id) REFERENCES users (id)
);

CREATE INDEX idx_client_comm_logs_client ON client_communication_logs (client_id, communicated_at DESC);
CREATE INDEX idx_client_comm_logs_user   ON client_communication_logs (owner_user_id);


-- =============================================================================
-- DOMAIN: Deals
-- =============================================================================

CREATE TABLE deals (
    id                              UUID                NOT NULL DEFAULT gen_random_uuid(),
    owner_user_id                   UUID                NOT NULL,
    client_id                       UUID                NOT NULL,
    title                           VARCHAR(500)        NOT NULL,
    stage                           deal_stage          NOT NULL DEFAULT 'new_lead',
    source                          deal_source,
    estimated_value                 NUMERIC(15,2),
    actual_value                    NUMERIC(15,2),
    currency                        CHAR(3)             NOT NULL DEFAULT 'VND',
    notes                           TEXT,
    ai_qualification_score          SMALLINT,
    ai_qualification_recommendation ai_recommendation,
    closed_at                       TIMESTAMPTZ,
    created_at                      TIMESTAMPTZ         NOT NULL DEFAULT NOW(),
    updated_at                      TIMESTAMPTZ         NOT NULL DEFAULT NOW(),
    deleted_at                      TIMESTAMPTZ,

    CONSTRAINT pk_deals PRIMARY KEY (id),
    CONSTRAINT fk_deals_user   FOREIGN KEY (owner_user_id) REFERENCES users (id),
    CONSTRAINT fk_deals_client FOREIGN KEY (client_id)     REFERENCES clients (id),
    CONSTRAINT chk_deals_qualification_score
        CHECK (ai_qualification_score IS NULL OR ai_qualification_score BETWEEN 0 AND 100)
);

CREATE INDEX idx_deals_owner_stage   ON deals (owner_user_id, stage);
CREATE INDEX idx_deals_owner_deleted ON deals (owner_user_id, deleted_at);
CREATE INDEX idx_deals_client        ON deals (client_id);
CREATE INDEX idx_deals_owner_created ON deals (owner_user_id, created_at DESC);
CREATE INDEX idx_deals_stage_closed  ON deals (stage, closed_at);

CREATE TRIGGER trg_deals_updated_at
    BEFORE UPDATE ON deals
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------

CREATE TABLE deal_activity_entries (
    id              UUID                NOT NULL DEFAULT gen_random_uuid(),
    deal_id         UUID                NOT NULL,
    owner_user_id   UUID                NOT NULL,
    entry_type      deal_activity_type  NOT NULL,
    description     TEXT                NOT NULL,
    previous_stage  deal_stage,
    new_stage       deal_stage,
    created_at      TIMESTAMPTZ         NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_deal_activity_entries PRIMARY KEY (id),
    CONSTRAINT fk_deal_activity_entries_deal FOREIGN KEY (deal_id)       REFERENCES deals (id),
    CONSTRAINT fk_deal_activity_entries_user FOREIGN KEY (owner_user_id) REFERENCES users (id)
);

CREATE INDEX idx_deal_activity_entries_deal ON deal_activity_entries (deal_id, created_at DESC);
CREATE INDEX idx_deal_activity_entries_user ON deal_activity_entries (owner_user_id);


-- =============================================================================
-- DOMAIN: Proposals
-- =============================================================================

CREATE TABLE proposals (
    id              UUID            NOT NULL DEFAULT gen_random_uuid(),
    deal_id         UUID            NOT NULL,
    owner_user_id   UUID            NOT NULL,
    version_number  INT             NOT NULL DEFAULT 1,
    status          proposal_status NOT NULL DEFAULT 'draft',
    content         JSONB           NOT NULL DEFAULT '{}',
    share_token     VARCHAR(255),
    share_expires_at TIMESTAMPTZ,
    sent_at         TIMESTAMPTZ,
    responded_at    TIMESTAMPTZ,
    ai_generated    BOOLEAN         NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_proposals PRIMARY KEY (id),
    CONSTRAINT fk_proposals_deal FOREIGN KEY (deal_id)       REFERENCES deals (id),
    CONSTRAINT fk_proposals_user FOREIGN KEY (owner_user_id) REFERENCES users (id),
    CONSTRAINT uq_proposals_deal_version UNIQUE (deal_id, version_number),
    CONSTRAINT chk_proposals_version CHECK (version_number > 0)
);

CREATE UNIQUE INDEX uq_proposals_share_token
    ON proposals (share_token)
    WHERE share_token IS NOT NULL;

CREATE INDEX idx_proposals_deal_status  ON proposals (deal_id, status);
CREATE INDEX idx_proposals_owner_status ON proposals (owner_user_id, status);
CREATE INDEX idx_proposals_owner_created ON proposals (owner_user_id, created_at DESC);
CREATE INDEX idx_proposals_content_gin  ON proposals USING GIN (content jsonb_path_ops);

CREATE TRIGGER trg_proposals_updated_at
    BEFORE UPDATE ON proposals
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- =============================================================================
-- DOMAIN: Contracts
-- =============================================================================

CREATE TABLE contracts (
    id                      UUID                NOT NULL DEFAULT gen_random_uuid(),
    deal_id                 UUID                NOT NULL,
    proposal_id             UUID                NOT NULL,
    client_id               UUID                NOT NULL,
    owner_user_id           UUID                NOT NULL,
    version_number          INT                 NOT NULL DEFAULT 1,
    status                  contract_status     NOT NULL DEFAULT 'draft',
    content                 JSONB               NOT NULL DEFAULT '{}',
    client_snapshot         JSONB               NOT NULL DEFAULT '{}',
    signed_by_freelancer_at TIMESTAMPTZ,
    signed_by_client_at     TIMESTAMPTZ,
    effective_date          DATE,
    end_date                DATE,
    share_token             VARCHAR(255),
    share_expires_at        TIMESTAMPTZ,
    parent_contract_id      UUID,
    ai_generated            BOOLEAN             NOT NULL DEFAULT FALSE,
    created_at              TIMESTAMPTZ         NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ         NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_contracts PRIMARY KEY (id),
    CONSTRAINT fk_contracts_deal     FOREIGN KEY (deal_id)           REFERENCES deals (id),
    CONSTRAINT fk_contracts_proposal FOREIGN KEY (proposal_id)       REFERENCES proposals (id),
    CONSTRAINT fk_contracts_client   FOREIGN KEY (client_id)         REFERENCES clients (id),
    CONSTRAINT fk_contracts_user     FOREIGN KEY (owner_user_id)     REFERENCES users (id),
    CONSTRAINT fk_contracts_parent   FOREIGN KEY (parent_contract_id) REFERENCES contracts (id),
    CONSTRAINT uq_contracts_deal_version UNIQUE (deal_id, version_number),
    CONSTRAINT chk_contracts_version CHECK (version_number > 0)
);

-- Enforce: only one active/pending contract per deal
CREATE UNIQUE INDEX uq_contracts_one_active_per_deal
    ON contracts (deal_id)
    WHERE status IN ('active', 'pending_signatures');

CREATE UNIQUE INDEX uq_contracts_share_token
    ON contracts (share_token)
    WHERE share_token IS NOT NULL;

CREATE INDEX idx_contracts_deal_status   ON contracts (deal_id, status);
CREATE INDEX idx_contracts_owner_status  ON contracts (owner_user_id, status);
CREATE INDEX idx_contracts_client        ON contracts (client_id);
CREATE INDEX idx_contracts_proposal      ON contracts (proposal_id);

CREATE TRIGGER trg_contracts_updated_at
    BEFORE UPDATE ON contracts
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------

CREATE TABLE contract_payment_milestones (
    id          UUID            NOT NULL DEFAULT gen_random_uuid(),
    contract_id UUID            NOT NULL,
    description TEXT            NOT NULL,
    amount      NUMERIC(15,2)   NOT NULL,
    due_date    DATE,
    invoice_id  UUID,           -- FK to invoices; added after invoices table
    sort_order  SMALLINT        NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_contract_payment_milestones PRIMARY KEY (id),
    CONSTRAINT fk_milestones_contract FOREIGN KEY (contract_id) REFERENCES contracts (id),
    CONSTRAINT chk_milestones_amount CHECK (amount > 0)
);

CREATE INDEX idx_milestones_contract ON contract_payment_milestones (contract_id, sort_order);

CREATE TRIGGER trg_milestones_updated_at
    BEFORE UPDATE ON contract_payment_milestones
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- =============================================================================
-- DOMAIN: Invoices
-- =============================================================================

CREATE TABLE invoices (
    id              UUID            NOT NULL DEFAULT gen_random_uuid(),
    owner_user_id   UUID            NOT NULL,
    client_id       UUID            NOT NULL,
    contract_id     UUID,
    deal_id         UUID,
    invoice_number  VARCHAR(100)    NOT NULL,
    status          invoice_status  NOT NULL DEFAULT 'draft',
    issue_date      DATE            NOT NULL,
    due_date        DATE            NOT NULL,
    currency        CHAR(3)         NOT NULL DEFAULT 'VND',
    subtotal        NUMERIC(15,2)   NOT NULL DEFAULT 0,
    tax_rate        NUMERIC(5,4)    NOT NULL DEFAULT 0,
    tax_amount      NUMERIC(15,2)   NOT NULL DEFAULT 0,
    total           NUMERIC(15,2)   NOT NULL DEFAULT 0,
    amount_paid     NUMERIC(15,2)   NOT NULL DEFAULT 0,
    notes           TEXT,
    client_snapshot JSONB           NOT NULL DEFAULT '{}',
    sent_at         TIMESTAMPTZ,
    voided_at       TIMESTAMPTZ,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_invoices PRIMARY KEY (id),
    CONSTRAINT fk_invoices_user     FOREIGN KEY (owner_user_id) REFERENCES users (id),
    CONSTRAINT fk_invoices_client   FOREIGN KEY (client_id)     REFERENCES clients (id),
    CONSTRAINT fk_invoices_contract FOREIGN KEY (contract_id)   REFERENCES contracts (id),
    CONSTRAINT fk_invoices_deal     FOREIGN KEY (deal_id)       REFERENCES deals (id),
    CONSTRAINT uq_invoices_number   UNIQUE (owner_user_id, invoice_number),
    CONSTRAINT chk_invoices_context CHECK (contract_id IS NOT NULL OR deal_id IS NOT NULL),
    CONSTRAINT chk_invoices_amount_paid CHECK (amount_paid <= total),
    CONSTRAINT chk_invoices_total   CHECK (total = subtotal + tax_amount),
    CONSTRAINT chk_invoices_tax_rate CHECK (tax_rate BETWEEN 0 AND 1)
);

CREATE INDEX idx_invoices_owner_status   ON invoices (owner_user_id, status);
CREATE INDEX idx_invoices_owner_due_date ON invoices (owner_user_id, due_date);
CREATE INDEX idx_invoices_owner_issued   ON invoices (owner_user_id, issue_date DESC);
CREATE INDEX idx_invoices_client         ON invoices (client_id);
CREATE INDEX idx_invoices_contract       ON invoices (contract_id) WHERE contract_id IS NOT NULL;
CREATE INDEX idx_invoices_deal           ON invoices (deal_id)     WHERE deal_id IS NOT NULL;

CREATE TRIGGER trg_invoices_updated_at
    BEFORE UPDATE ON invoices
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Now that invoices exists, add the FK from contract_payment_milestones
ALTER TABLE contract_payment_milestones
    ADD CONSTRAINT fk_milestones_invoice
    FOREIGN KEY (invoice_id) REFERENCES invoices (id);

CREATE INDEX idx_milestones_invoice
    ON contract_payment_milestones (invoice_id)
    WHERE invoice_id IS NOT NULL;

-- ---------------------------------------------------------------------------

CREATE TABLE invoice_line_items (
    id          UUID            NOT NULL DEFAULT gen_random_uuid(),
    invoice_id  UUID            NOT NULL,
    description TEXT            NOT NULL,
    quantity    NUMERIC(10,4)   NOT NULL DEFAULT 1,
    unit_price  NUMERIC(15,2)   NOT NULL,
    amount      NUMERIC(15,2)   NOT NULL,
    sort_order  SMALLINT        NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_invoice_line_items PRIMARY KEY (id),
    CONSTRAINT fk_invoice_line_items_invoice FOREIGN KEY (invoice_id) REFERENCES invoices (id),
    CONSTRAINT chk_line_items_quantity CHECK (quantity > 0)
);

CREATE INDEX idx_invoice_line_items_invoice ON invoice_line_items (invoice_id, sort_order);

-- ---------------------------------------------------------------------------

CREATE TABLE invoice_payment_records (
    id              UUID            NOT NULL DEFAULT gen_random_uuid(),
    invoice_id      UUID            NOT NULL,
    amount          NUMERIC(15,2)   NOT NULL,
    payment_date    DATE            NOT NULL,
    payment_method  payment_method  NOT NULL DEFAULT 'other',
    reference_note  TEXT,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_invoice_payment_records PRIMARY KEY (id),
    CONSTRAINT fk_invoice_payment_records_invoice FOREIGN KEY (invoice_id) REFERENCES invoices (id),
    CONSTRAINT chk_payment_records_amount CHECK (amount > 0)
);

CREATE INDEX idx_invoice_payment_records_invoice
    ON invoice_payment_records (invoice_id, payment_date DESC);


-- =============================================================================
-- DOMAIN: Reminders
-- =============================================================================

CREATE TABLE reminders (
    id                  UUID                    NOT NULL DEFAULT gen_random_uuid(),
    owner_user_id       UUID                    NOT NULL,
    target_type         reminder_target_type    NOT NULL,
    target_id           UUID                    NOT NULL,
    reminder_type       reminder_type_enum      NOT NULL,
    channel             notification_channel    NOT NULL DEFAULT 'both',
    status              reminder_status         NOT NULL DEFAULT 'pending',
    scheduled_at        TIMESTAMPTZ             NOT NULL,
    message_preview     TEXT,
    recurrence_rule     TEXT,
    parent_reminder_id  UUID,
    retry_count         SMALLINT                NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ             NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ             NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_reminders PRIMARY KEY (id),
    CONSTRAINT fk_reminders_user   FOREIGN KEY (owner_user_id)      REFERENCES users (id),
    CONSTRAINT fk_reminders_parent FOREIGN KEY (parent_reminder_id) REFERENCES reminders (id),
    CONSTRAINT chk_reminders_retry CHECK (retry_count BETWEEN 0 AND 3)
);

-- Worker pickup: pending reminders ordered by scheduled time
CREATE INDEX idx_reminders_owner_status_scheduled
    ON reminders (owner_user_id, status, scheduled_at);

-- Cancel-on-event: find all pending reminders for a given business object
CREATE INDEX idx_reminders_target
    ON reminders (target_type, target_id);

-- Scheduler scan: pending reminders due for execution
CREATE INDEX idx_reminders_pending_scheduled
    ON reminders (scheduled_at)
    WHERE status = 'pending';

CREATE INDEX idx_reminders_parent
    ON reminders (parent_reminder_id)
    WHERE parent_reminder_id IS NOT NULL;

CREATE TRIGGER trg_reminders_updated_at
    BEFORE UPDATE ON reminders
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------

CREATE TABLE reminder_delivery_records (
    id              UUID                    NOT NULL DEFAULT gen_random_uuid(),
    reminder_id     UUID                    NOT NULL,
    attempted_at    TIMESTAMPTZ             NOT NULL DEFAULT NOW(),
    channel         notification_channel    NOT NULL,
    outcome         reminder_outcome        NOT NULL,
    error_message   TEXT,

    CONSTRAINT pk_reminder_delivery_records PRIMARY KEY (id),
    CONSTRAINT fk_reminder_delivery_records_reminder
        FOREIGN KEY (reminder_id) REFERENCES reminders (id)
);

CREATE INDEX idx_reminder_delivery_records_reminder
    ON reminder_delivery_records (reminder_id, attempted_at DESC);


-- =============================================================================
-- DOMAIN: Analytics (Read-Optimized Snapshots)
-- =============================================================================

CREATE TABLE revenue_snapshots (
    id                  UUID            NOT NULL DEFAULT gen_random_uuid(),
    owner_user_id       UUID            NOT NULL,
    period_type         period_type     NOT NULL,
    period_start        DATE            NOT NULL,
    period_end          DATE            NOT NULL,
    total_invoiced      NUMERIC(15,2)   NOT NULL DEFAULT 0,
    total_collected     NUMERIC(15,2)   NOT NULL DEFAULT 0,
    total_outstanding   NUMERIC(15,2)   NOT NULL DEFAULT 0,
    total_overdue       NUMERIC(15,2)   NOT NULL DEFAULT 0,
    computed_at         TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_revenue_snapshots PRIMARY KEY (id),
    CONSTRAINT fk_revenue_snapshots_user FOREIGN KEY (owner_user_id) REFERENCES users (id),
    CONSTRAINT uq_revenue_snapshots UNIQUE (owner_user_id, period_type, period_start)
);

CREATE INDEX idx_revenue_snapshots_owner ON revenue_snapshots (owner_user_id, period_type, period_start DESC);

-- ---------------------------------------------------------------------------

CREATE TABLE pipeline_snapshots (
    id              UUID            NOT NULL DEFAULT gen_random_uuid(),
    owner_user_id   UUID            NOT NULL,
    stage           deal_stage      NOT NULL,
    deal_count      INT             NOT NULL DEFAULT 0,
    total_value     NUMERIC(15,2)   NOT NULL DEFAULT 0,
    snapshot_date   DATE            NOT NULL,
    computed_at     TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_pipeline_snapshots PRIMARY KEY (id),
    CONSTRAINT fk_pipeline_snapshots_user FOREIGN KEY (owner_user_id) REFERENCES users (id),
    CONSTRAINT uq_pipeline_snapshots UNIQUE (owner_user_id, stage, snapshot_date)
);

CREATE INDEX idx_pipeline_snapshots_owner ON pipeline_snapshots (owner_user_id, snapshot_date DESC);


-- =============================================================================
-- DOMAIN: Admin
-- =============================================================================

CREATE TABLE audit_log_entries (
    id              UUID        NOT NULL DEFAULT gen_random_uuid(),
    event_type      VARCHAR(100) NOT NULL,
    actor_user_id   UUID,
    target_type     VARCHAR(100),
    target_id       UUID,
    description     TEXT        NOT NULL,
    ip_address      INET,
    metadata        JSONB,
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_audit_log_entries PRIMARY KEY (id),
    CONSTRAINT fk_audit_log_entries_actor FOREIGN KEY (actor_user_id) REFERENCES users (id)
);

CREATE INDEX idx_audit_log_actor    ON audit_log_entries (actor_user_id, occurred_at DESC);
CREATE INDEX idx_audit_log_target   ON audit_log_entries (target_type, target_id, occurred_at DESC);
CREATE INDEX idx_audit_log_event    ON audit_log_entries (event_type, occurred_at DESC);

-- ---------------------------------------------------------------------------

CREATE TABLE system_templates (
    id                  UUID            NOT NULL DEFAULT gen_random_uuid(),
    template_type       template_type   NOT NULL,
    name                VARCHAR(255)    NOT NULL,
    content             JSONB           NOT NULL,
    plan_tier_required  VARCHAR(50),
    version_number      INT             NOT NULL DEFAULT 1,
    is_active           BOOLEAN         NOT NULL DEFAULT FALSE,
    parent_template_id  UUID,
    created_by_admin_id UUID            NOT NULL,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_system_templates PRIMARY KEY (id),
    CONSTRAINT fk_system_templates_admin  FOREIGN KEY (created_by_admin_id) REFERENCES users (id),
    CONSTRAINT fk_system_templates_parent FOREIGN KEY (parent_template_id)  REFERENCES system_templates (id),
    CONSTRAINT chk_system_templates_version CHECK (version_number > 0)
);

CREATE INDEX idx_system_templates_type_active ON system_templates (template_type, is_active);
CREATE INDEX idx_system_templates_parent
    ON system_templates (parent_template_id)
    WHERE parent_template_id IS NOT NULL;

CREATE TRIGGER trg_system_templates_updated_at
    BEFORE UPDATE ON system_templates
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------

CREATE TABLE feature_flags (
    id                  UUID        NOT NULL DEFAULT gen_random_uuid(),
    flag_name           VARCHAR(100) NOT NULL,
    is_enabled          BOOLEAN     NOT NULL DEFAULT FALSE,
    rollout_percentage  SMALLINT    NOT NULL DEFAULT 0,
    target_user_ids     UUID[],
    description         TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_feature_flags PRIMARY KEY (id),
    CONSTRAINT uq_feature_flags_name UNIQUE (flag_name),
    CONSTRAINT chk_feature_flags_rollout CHECK (rollout_percentage BETWEEN 0 AND 100)
);

CREATE TRIGGER trg_feature_flags_updated_at
    BEFORE UPDATE ON feature_flags
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------

CREATE TABLE ai_cost_records (
    id                  UUID                    NOT NULL DEFAULT gen_random_uuid(),
    user_id             UUID                    NOT NULL,
    ai_module           ai_module_type          NOT NULL,
    model_used          VARCHAR(100)            NOT NULL,
    input_tokens        INT                     NOT NULL DEFAULT 0,
    output_tokens       INT                     NOT NULL DEFAULT 0,
    estimated_cost_usd  NUMERIC(10,6)           NOT NULL DEFAULT 0,
    status              ai_generation_status    NOT NULL DEFAULT 'completed',
    input_hash          CHAR(64),
    occurred_at         TIMESTAMPTZ             NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_ai_cost_records PRIMARY KEY (id),
    CONSTRAINT fk_ai_cost_records_user FOREIGN KEY (user_id) REFERENCES users (id),
    CONSTRAINT chk_ai_cost_records_tokens CHECK (input_tokens >= 0 AND output_tokens >= 0),
    CONSTRAINT chk_ai_cost_records_cost   CHECK (estimated_cost_usd >= 0)
);

CREATE INDEX idx_ai_cost_records_user    ON ai_cost_records (user_id, occurred_at DESC);
CREATE INDEX idx_ai_cost_records_module  ON ai_cost_records (ai_module, occurred_at DESC);
CREATE INDEX idx_ai_cost_records_time    ON ai_cost_records (occurred_at DESC);


-- =============================================================================
-- Seed: Default subscription plan
-- =============================================================================

INSERT INTO subscription_plans (
    id, name, slug, price_monthly, currency,
    max_ai_generations_per_month, can_use_ai, can_export_pdf,
    max_clients, max_deals, is_active
) VALUES (
    gen_random_uuid(), 'Free', 'free', 0, 'USD',
    0, FALSE, FALSE,
    10, 10, TRUE
);
