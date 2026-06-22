"""SQLAlchemy ORM models — all tables in one module.

Import this module wherever ORM models are needed, and in alembic/env.py
so autogenerate picks up every table.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, INET, JSONB, UUID
from sqlalchemy.dialects.postgresql import ENUM as PgEnum  # noqa: N811
from sqlalchemy.orm import Mapped, column_property, mapped_column, relationship

from src.infrastructure.database.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin

# ---------------------------------------------------------------------------
# PostgreSQL ENUM types (create_type=False — created by Alembic migrations)
# ---------------------------------------------------------------------------
_user_role = PgEnum("freelancer", "admin", name="user_role", create_type=False)
_user_status = PgEnum("active", "suspended", "deleted", name="user_status", create_type=False)
_notification_channel = PgEnum(
    "email", "in_app", "both", "zalo", name="notification_channel", create_type=False
)
_theme_preference = PgEnum("light", "dark", name="theme_preference", create_type=False)
_subscription_status = PgEnum(
    "active", "past_due", "suspended", "cancelled",
    name="subscription_status", create_type=False,
)
_billing_event_type = PgEnum(
    "payment_succeeded", "payment_failed",
    "subscription_renewed", "subscription_cancelled",
    name="billing_event_type", create_type=False,
)
_client_type = PgEnum("individual", "company", name="client_type", create_type=False)
_client_status = PgEnum(
    "prospect", "active", "inactive", "archived", name="client_status", create_type=False
)
_comm_channel = PgEnum(
    "email", "phone", "meeting", "message", "zalo", name="comm_channel", create_type=False
)
_deal_stage = PgEnum(
    "new_lead", "qualified", "proposal_sent", "in_negotiation",
    "active", "completed_and_billed", "lost",
    name="deal_stage", create_type=False,
)
_deal_source = PgEnum(
    "inbound", "referral", "outreach", "platform", "other",
    name="deal_source", create_type=False,
)
_deal_activity_type = PgEnum(
    "stage_change",
    "note_added",
    "document_attached",
    "ai_qualification",
    name="deal_activity_type",
    create_type=False,
)
_ai_recommendation = PgEnum("qualify", "pass", name="ai_recommendation", create_type=False)
_lead_score_level = PgEnum("hot", "warm", "cold", name="lead_score_level", create_type=False)
_proposal_status = PgEnum(
    "draft",
    "sent",
    "accepted",
    "rejected",
    "expired",
    "superseded",
    name="proposal_status",
    create_type=False,
)
_contract_status = PgEnum(
    "draft",
    "pending_signatures",
    "active",
    "completed",
    "terminated",
    "expired",
    "archived",
    name="contract_status",
    create_type=False,
)
_invoice_status = PgEnum(
    "draft", "sent", "partially_paid", "paid", "overdue", "void",
    name="invoice_status", create_type=False,
)
_payment_method = PgEnum(
    "bank_transfer", "momo", "cash", "online", "other", name="payment_method", create_type=False
)
_reminder_target_type = PgEnum(
    "deal", "client", "invoice", "contract", name="reminder_target_type", create_type=False
)
_reminder_type_enum = PgEnum(
    "follow_up",
    "proposal_follow_up",
    "contract_signing_nudge",
    "payment_due",
    "payment_overdue",
    "re_engagement",
    "custom",
    name="reminder_type_enum",
    create_type=False,
)
_reminder_status = PgEnum(
    "pending", "sent", "failed", "cancelled", "skipped",
    name="reminder_status", create_type=False,
)
_reminder_outcome = PgEnum("success", "failure", name="reminder_outcome", create_type=False)
_period_type = PgEnum("monthly", "quarterly", "yearly", name="period_type", create_type=False)
_template_type = PgEnum("proposal", "contract", name="template_type", create_type=False)
_ai_module_type = PgEnum(
    "lead_qualifier", "proposal_generator", "contract_generator", "followup_generator",
    name="ai_module_type", create_type=False,
)
_ai_generation_status = PgEnum(
    "pending", "completed", "failed", name="ai_generation_status", create_type=False
)


# =============================================================================
# DOMAIN: Identity & Access
# =============================================================================

class UserModel(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(_user_role, nullable=False, server_default="freelancer")
    status: Mapped[str] = mapped_column(_user_status, nullable=False, server_default="active")
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Professional profile
    skills: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    specialization: Mapped[str | None] = mapped_column(String(255), nullable=True)
    default_hourly_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="VND")
    portfolio_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Public freelancer directory
    professional_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    service_categories: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    is_listed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    # Payment info
    momo_phone_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    bank_account_info: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Preferences
    locale: Mapped[str] = mapped_column(String(5), nullable=False, server_default="vi")
    timezone: Mapped[str] = mapped_column(
        String(100), nullable=False, server_default="Asia/Ho_Chi_Minh"
    )
    notification_channel: Mapped[str] = mapped_column(
        _notification_channel, nullable=False, server_default="both"
    )
    theme: Mapped[str] = mapped_column(_theme_preference, nullable=False, server_default="light")

    # Zalo OA integration
    zalo_oa_app_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    zalo_oa_access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    zalo_oa_refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Public intake form — hard-to-guess token the client uses to self-submit a lead
    # (POST /api/v1/intake/{share_token}). Generated at registration. Nullable so
    # pre-existing rows stay valid; the UNIQUE constraint permits multiple NULLs in PG.
    intake_share_token: Mapped[str | None] = mapped_column(String(64), nullable=True)

    subscription: Mapped["SubscriptionModel | None"] = relationship(
        "SubscriptionModel", back_populates="user", foreign_keys="SubscriptionModel.user_id"
    )

    __table_args__ = (
        Index("idx_users_status_deleted", "status", "deleted_at"),
        UniqueConstraint("intake_share_token", name="uq_users_intake_share_token"),
    )


class OAuthIdentityModel(UUIDMixin, Base):
    __tablename__ = "oauth_identities"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("provider", "provider_sub", name="uq_oauth_identities_provider_sub"),
        Index("idx_oauth_identities_user_id", "user_id"),
    )


class RefreshTokenModel(UUIDMixin, Base):
    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    device_hint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_refresh_tokens_user_validity", "user_id", "expires_at", "revoked_at"),
    )


class PasswordResetTokenModel(UUIDMixin, Base):
    __tablename__ = "password_reset_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_password_reset_tokens_user", "user_id", "expires_at"),
    )


class TokenBlacklistModel(UUIDMixin, Base):
    __tablename__ = "token_blacklist"

    jti: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    blacklisted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("idx_token_blacklist_expires", "expires_at"),)


# =============================================================================
# DOMAIN: Subscriptions
# =============================================================================

class PlanModel(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "subscription_plans"

    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    price_monthly: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, server_default="0"
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="USD")
    max_ai_generations_per_month: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    can_use_ai: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    can_export_pdf: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    max_clients: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_deals: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    __table_args__ = (
        CheckConstraint("price_monthly >= 0", name="chk_subscription_plans_price"),
        Index("idx_subscription_plans_active", "is_active"),
    )


class SubscriptionModel(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "subscriptions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, unique=True
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subscription_plans.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        _subscription_status, nullable=False, server_default="active"
    )
    current_period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    current_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cancel_at_period_end: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, unique=True
    )
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    override_by_admin_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    override_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped["UserModel"] = relationship(
        "UserModel", back_populates="subscription", foreign_keys=[user_id]
    )

    __table_args__ = (
        Index("idx_subscriptions_plan_status", "plan_id", "status"),
        Index("idx_subscriptions_period_end", "current_period_end"),
    )


class UsageRecordModel(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "usage_records"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subscriptions.id"), nullable=False
    )
    billing_period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    billing_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ai_generations_used: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )

    __table_args__ = (
        UniqueConstraint("user_id", "billing_period_start", name="uq_usage_records_user_period"),
        CheckConstraint("ai_generations_used >= 0", name="chk_usage_records_count"),
        Index("idx_usage_records_subscription", "subscription_id"),
    )


class BillingEventModel(UUIDMixin, Base):
    __tablename__ = "billing_events"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subscriptions.id"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(_billing_event_type, nullable=False)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    stripe_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    event_metadata: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_billing_events_user", "user_id", "occurred_at"),
        Index("idx_billing_events_subscription", "subscription_id"),
    )


# =============================================================================
# DOMAIN: Clients
# =============================================================================

class ClientModel(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "clients"

    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    type: Mapped[str] = mapped_column(_client_type, nullable=False, server_default="individual")
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    website: Mapped[str | None] = mapped_column(Text, nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    address_city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    address_country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(_client_status, nullable=False, server_default="prospect")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("idx_clients_owner_status", "owner_user_id", "status"),
        Index("idx_clients_owner_deleted", "owner_user_id", "deleted_at"),
    )


class ClientCommunicationLogModel(UUIDMixin, Base):
    __tablename__ = "client_communication_logs"

    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    channel: Mapped[str] = mapped_column(_comm_channel, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    communicated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_client_comm_logs_client", "client_id", "communicated_at"),
        Index("idx_client_comm_logs_user", "owner_user_id"),
    )


# =============================================================================
# DOMAIN: Deals
# =============================================================================

class DealModel(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "deals"

    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    stage: Mapped[str] = mapped_column(_deal_stage, nullable=False, server_default="new_lead")
    source: Mapped[str | None] = mapped_column(_deal_source, nullable=True)
    estimated_value: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    actual_value: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="VND")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    project_type: Mapped[str | None] = mapped_column(String(200), nullable=True)
    service_category: Mapped[str | None] = mapped_column(String(200), nullable=True)
    pricing_tier: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ai_qualification_score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    ai_qualification_confidence: Mapped[float | None] = mapped_column(nullable=True)
    ai_qualification_recommendation: Mapped[str | None] = mapped_column(
        _ai_recommendation, nullable=True
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "ai_qualification_score IS NULL OR ai_qualification_score BETWEEN 0 AND 100",
            name="chk_deals_qualification_score",
        ),
        Index("idx_deals_owner_stage", "owner_user_id", "stage"),
        Index("idx_deals_owner_deleted", "owner_user_id", "deleted_at"),
        Index("idx_deals_client", "client_id"),
        Index("idx_deals_owner_created", "owner_user_id", "created_at"),
        Index("idx_deals_stage_closed", "stage", "closed_at"),
    )


# Computed column — must be defined after DealModel so both sides of the FK exist.
ClientModel.deal_count = column_property(
    select(func.count(DealModel.id))
    .where(DealModel.client_id == ClientModel.id)
    .where(DealModel.deleted_at.is_(None))
    .correlate_except(DealModel)
    .scalar_subquery()
)


class DealIntakeModel(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "deal_intakes"

    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )

    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clients.id"),
        nullable=False,
    )

    inquiry_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    estimated_budget: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    desired_timeline: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    source: Mapped[str | None] = mapped_column(
        _deal_source,
        nullable=True,
    )

    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_deal_intakes_owner", "owner_user_id"),
        Index("idx_deal_intakes_client", "client_id"),
        Index("idx_deal_intakes_submitted", "submitted_at"),
        Index("idx_deal_intakes_owner_deleted", "owner_user_id", "deleted_at"),
    )

class DealActivityEntryModel(UUIDMixin, Base):
    __tablename__ = "deal_activity_entries"

    deal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("deals.id"), nullable=False
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    entry_type: Mapped[str] = mapped_column(_deal_activity_type, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    previous_stage: Mapped[str | None] = mapped_column(_deal_stage, nullable=True)
    new_stage: Mapped[str | None] = mapped_column(_deal_stage, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_deal_activity_entries_deal", "deal_id", "created_at"),
        Index("idx_deal_activity_entries_user", "owner_user_id"),
    )


class LeadScoreModel(Base):
    __tablename__ = "lead_scores"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    deal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("deals.id"), nullable=False
    )
    score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    project_type: Mapped[str | None] = mapped_column(String(200), nullable=True)
    budget_signal: Mapped[str | None] = mapped_column(String(200), nullable=True)
    timeline_signal: Mapped[str | None] = mapped_column(String(200), nullable=True)
    urgency_signal: Mapped[str | None] = mapped_column(String(200), nullable=True)
    red_flags: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index("idx_lead_scores_deal", "deal_id"),
        CheckConstraint("score BETWEEN 0 AND 100", name="ck_lead_scores_score_range"),
        CheckConstraint("confidence BETWEEN 0.0 AND 1.0", name="ck_lead_scores_confidence_range"),
    )


class ProjectModel(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "projects"

    deal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("deals.id"), nullable=False
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("idx_projects_deal", "deal_id"),
        Index("idx_projects_owner", "owner_user_id"),
        Index("idx_projects_owner_deal", "owner_user_id", "deal_id"),
    )


class TaskModel(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "tasks"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_done: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    __table_args__ = (
        Index("idx_tasks_project", "project_id"),
        Index("idx_tasks_owner_project", "owner_user_id", "project_id"),
    )


# =============================================================================
# DOMAIN: Proposals
# =============================================================================

class ProposalModel(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "proposals"

    deal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("deals.id"), nullable=False
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    status: Mapped[str] = mapped_column(_proposal_status, nullable=False, server_default="draft")
    content: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'"))
    share_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    share_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ai_generated: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    __table_args__ = (
        UniqueConstraint("deal_id", "version_number", name="uq_proposals_deal_version"),
        CheckConstraint("version_number > 0", name="chk_proposals_version"),
        Index("idx_proposals_deal_status", "deal_id", "status"),
        Index("idx_proposals_owner_status", "owner_user_id", "status"),
        Index("idx_proposals_owner_created", "owner_user_id", "created_at"),
        Index(
            "idx_proposals_content_gin", "content",
            postgresql_using="gin",
            postgresql_ops={"content": "jsonb_path_ops"},
        ),
    )


# =============================================================================
# DOMAIN: Contracts
# =============================================================================

class ContractModel(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "contracts"

    deal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("deals.id"), nullable=False
    )
    proposal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("proposals.id"), nullable=False
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    status: Mapped[str] = mapped_column(_contract_status, nullable=False, server_default="draft")
    content: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'"))
    client_snapshot: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'")
    )
    signed_by_freelancer_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    signed_by_client_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    share_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    share_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    parent_contract_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contracts.id"), nullable=True
    )
    ai_generated: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    __table_args__ = (
        UniqueConstraint("deal_id", "version_number", name="uq_contracts_deal_version"),
        CheckConstraint("version_number > 0", name="chk_contracts_version"),
        Index("idx_contracts_deal_status", "deal_id", "status"),
        Index("idx_contracts_owner_status", "owner_user_id", "status"),
        Index("idx_contracts_client", "client_id"),
        Index("idx_contracts_proposal", "proposal_id"),
        Index(
            "uq_contracts_one_active_per_deal", "deal_id",
            unique=True,
            postgresql_where=text("status IN ('active', 'pending_signatures')"),
        ),
    )


class ContractPaymentMilestoneModel(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "contract_payment_milestones"

    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contracts.id"), nullable=False
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=True
    )
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")

    __table_args__ = (
        CheckConstraint("amount > 0", name="chk_milestones_amount"),
        Index("idx_milestones_contract", "contract_id", "sort_order"),
    )


# =============================================================================
# DOMAIN: Invoices
# =============================================================================

class InvoiceModel(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "invoices"

    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False
    )
    contract_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contracts.id"), nullable=True
    )
    deal_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("deals.id"), nullable=True
    )
    invoice_number: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(_invoice_status, nullable=False, server_default="draft")
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="VND")
    subtotal: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, server_default="0"
    )
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, server_default="0")
    tax_amount: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, server_default="0"
    )
    total: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default="0")
    amount_paid: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, server_default="0"
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    client_snapshot: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'")
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    share_token: Mapped[str | None] = mapped_column(String(128), nullable=True)

    __table_args__ = (
        UniqueConstraint("owner_user_id", "invoice_number", name="uq_invoices_number"),
        UniqueConstraint("share_token", name="uq_invoices_share_token"),
        Index("idx_invoices_share_token", "share_token"),
        CheckConstraint(
            "contract_id IS NOT NULL OR deal_id IS NOT NULL", name="chk_invoices_context"
        ),
        CheckConstraint("amount_paid <= total", name="chk_invoices_amount_paid"),
        CheckConstraint("total = subtotal + tax_amount", name="chk_invoices_total"),
        CheckConstraint("tax_rate BETWEEN 0 AND 1", name="chk_invoices_tax_rate"),
        Index("idx_invoices_owner_status", "owner_user_id", "status"),
        Index("idx_invoices_owner_due_date", "owner_user_id", "due_date"),
        Index("idx_invoices_owner_issued", "owner_user_id", "issue_date"),
        Index("idx_invoices_client", "client_id"),
        Index(
            "idx_invoices_contract", "contract_id",
            postgresql_where=text("contract_id IS NOT NULL"),
        ),
        Index(
            "idx_invoices_deal", "deal_id",
            postgresql_where=text("deal_id IS NOT NULL"),
        ),
    )


class InvoiceLineItemModel(UUIDMixin, Base):
    __tablename__ = "invoice_line_items"

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=False
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, server_default="1")
    unit_price: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("quantity > 0", name="chk_line_items_quantity"),
        Index("idx_invoice_line_items_invoice", "invoice_id", "sort_order"),
    )


class InvoicePaymentRecordModel(UUIDMixin, Base):
    __tablename__ = "invoice_payment_records"

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    payment_method: Mapped[str] = mapped_column(
        _payment_method, nullable=False, server_default="other"
    )
    reference_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("amount > 0", name="chk_payment_records_amount"),
        Index("idx_invoice_payment_records_invoice", "invoice_id", "payment_date"),
    )


# =============================================================================
# DOMAIN: Reminders
# =============================================================================

class ReminderModel(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "reminders"

    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    target_type: Mapped[str] = mapped_column(_reminder_target_type, nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    reminder_type: Mapped[str] = mapped_column(_reminder_type_enum, nullable=False)
    channel: Mapped[str] = mapped_column(
        _notification_channel, nullable=False, server_default="both"
    )
    status: Mapped[str] = mapped_column(
        _reminder_status, nullable=False, server_default="pending"
    )
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    message_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    recurrence_rule: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_reminder_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reminders.id"), nullable=True
    )
    retry_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")

    __table_args__ = (
        CheckConstraint("retry_count BETWEEN 0 AND 3", name="chk_reminders_retry"),
        Index(
            "idx_reminders_owner_status_scheduled",
            "owner_user_id", "status", "scheduled_at",
        ),
        Index("idx_reminders_target", "target_type", "target_id"),
        Index(
            "idx_reminders_pending_scheduled", "scheduled_at",
            postgresql_where=text("status = 'pending'"),
        ),
        Index(
            "idx_reminders_parent", "parent_reminder_id",
            postgresql_where=text("parent_reminder_id IS NOT NULL"),
        ),
    )


class ReminderDeliveryRecordModel(UUIDMixin, Base):
    __tablename__ = "reminder_delivery_records"

    reminder_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reminders.id"), nullable=False
    )
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    channel: Mapped[str] = mapped_column(_notification_channel, nullable=False)
    outcome: Mapped[str] = mapped_column(_reminder_outcome, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("idx_reminder_delivery_records_reminder", "reminder_id", "attempted_at"),
    )


# =============================================================================
# DOMAIN: Analytics
# =============================================================================

class RevenueSnapshotModel(UUIDMixin, Base):
    __tablename__ = "revenue_snapshots"

    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    period_type: Mapped[str] = mapped_column(_period_type, nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    total_invoiced: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, server_default="0"
    )
    total_collected: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, server_default="0"
    )
    total_outstanding: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, server_default="0"
    )
    total_overdue: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, server_default="0"
    )
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "owner_user_id", "period_type", "period_start", name="uq_revenue_snapshots"
        ),
        Index("idx_revenue_snapshots_owner", "owner_user_id", "period_type", "period_start"),
    )


class PipelineSnapshotModel(UUIDMixin, Base):
    __tablename__ = "pipeline_snapshots"

    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    stage: Mapped[str] = mapped_column(_deal_stage, nullable=False)
    deal_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    total_value: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, server_default="0"
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "owner_user_id", "stage", "snapshot_date", name="uq_pipeline_snapshots"
        ),
        Index("idx_pipeline_snapshots_owner", "owner_user_id", "snapshot_date"),
    )


# =============================================================================
# DOMAIN: Admin
# =============================================================================

class AuditLogEntryModel(UUIDMixin, Base):
    __tablename__ = "audit_log_entries"

    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    target_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    log_metadata: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_audit_log_actor", "actor_user_id", "occurred_at"),
        Index("idx_audit_log_target", "target_type", "target_id", "occurred_at"),
        Index("idx_audit_log_event", "event_type", "occurred_at"),
    )


class SystemTemplateModel(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "system_templates"

    template_type: Mapped[str] = mapped_column(_template_type, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    plan_tier_required: Mapped[str | None] = mapped_column(String(50), nullable=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    parent_template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("system_templates.id"), nullable=True
    )
    created_by_admin_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    __table_args__ = (
        CheckConstraint("version_number > 0", name="chk_system_templates_version"),
        Index("idx_system_templates_type_active", "template_type", "is_active"),
    )


class FeatureFlagModel(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "feature_flags"

    flag_name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    rollout_percentage: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default="0"
    )
    target_user_ids: Mapped[list[uuid.UUID] | None] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "rollout_percentage BETWEEN 0 AND 100", name="chk_feature_flags_rollout"
        ),
    )


class AiCostRecordModel(UUIDMixin, Base):
    __tablename__ = "ai_cost_records"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    ai_module: Mapped[str] = mapped_column(_ai_module_type, nullable=False)
    model_used: Mapped[str] = mapped_column(String(100), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    estimated_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 6), nullable=False, server_default="0"
    )
    status: Mapped[str] = mapped_column(
        _ai_generation_status, nullable=False, server_default="completed"
    )
    input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0", name="chk_ai_cost_records_tokens"
        ),
        CheckConstraint("estimated_cost_usd >= 0", name="chk_ai_cost_records_cost"),
        Index("idx_ai_cost_records_user", "user_id", "occurred_at"),
        Index("idx_ai_cost_records_module", "ai_module", "occurred_at"),
        Index("idx_ai_cost_records_time", "occurred_at"),
    )
