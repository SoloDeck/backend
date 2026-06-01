"""SQLAlchemy ORM models — all tables in one module.

Import this module wherever you need to reference models, or in alembic/env.py
so autogenerate picks up every table.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin


# =============================================================================
# DOMAIN: Identity & Access
# =============================================================================

class UserModel(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, server_default="freelancer")
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="active")

    # hashed_password is NULL for OAuth-only accounts
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)

    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Professional profile (embedded value object)
    skills: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    specialization: Mapped[str | None] = mapped_column(String(255), nullable=True)
    default_hourly_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="VND")
    portfolio_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Preferences (embedded value object)
    locale: Mapped[str] = mapped_column(String(5), nullable=False, server_default="vi")
    timezone: Mapped[str] = mapped_column(String(100), nullable=False, server_default="Asia/Ho_Chi_Minh")
    notification_channel: Mapped[str] = mapped_column(String(20), nullable=False, server_default="both")
    theme: Mapped[str] = mapped_column(String(20), nullable=False, server_default="light")

    subscription: Mapped["SubscriptionModel | None"] = relationship(
        "SubscriptionModel", back_populates="user", uselist=False
    )

    __table_args__ = (
        Index("idx_users_status_deleted", "status", "deleted_at"),
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

    __table_args__ = (
        Index("idx_token_blacklist_expires", "expires_at"),
    )


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
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="active")
    current_period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
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
