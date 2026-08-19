"""SQLAlchemy ORM models — all tables in one module.

Import this module wherever ORM models are needed, and in alembic/env.py
so autogenerate picks up every table.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
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
    text, JSON,
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
    "active",
    "past_due",
    "suspended",
    "cancelled",
    name="subscription_status",
    create_type=False,
)
_billing_event_type = PgEnum(
    "payment_succeeded",
    "payment_failed",
    "subscription_renewed",
    "subscription_cancelled",
    "subscription_expired",
    "subscription_upgraded",
    "subscription_downgrade_scheduled",
    name="billing_event_type",
    create_type=False,
)
_payment_provider = PgEnum(
    "momo", "bank_transfer", "vnpay", "manual", name="payment_provider", create_type=False
)
_subscription_payment_status = PgEnum(
    "pending",
    "processing",
    "succeeded",
    "failed",
    "expired",
    "cancelled",
    name="subscription_payment_status",
    create_type=False,
)
_client_type = PgEnum("individual", "company", name="client_type", create_type=False)
_client_status = PgEnum(
    "prospect", "active", "inactive", "archived", name="client_status", create_type=False
)
_comm_channel = PgEnum(
    "email", "phone", "meeting", "message", "zalo", name="comm_channel", create_type=False
)
_deal_stage = PgEnum(
    "new_lead",
    "qualified",
    "proposal_sent",
    "in_negotiation",
    "active",
    "completed_and_billed",
    "lost",
    name="deal_stage",
    create_type=False,
)
_deal_source = PgEnum(
    "inbound",
    "referral",
    "outreach",
    "platform",
    "other",
    name="deal_source",
    create_type=False,
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
    "draft",
    "sent",
    "partially_paid",
    "paid",
    "overdue",
    "void",
    name="invoice_status",
    create_type=False,
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
    "pending",
    "sent",
    "failed",
    "cancelled",
    "skipped",
    name="reminder_status",
    create_type=False,
)
_reminder_outcome = PgEnum("success", "failure", name="reminder_outcome", create_type=False)
_period_type = PgEnum("monthly", "quarterly", "yearly", name="period_type", create_type=False)
_template_type = PgEnum("proposal", "contract", name="template_type", create_type=False)
_ai_module_type = PgEnum(
    "lead_qualifier",
    "proposal_generator",
    "contract_generator",
    "followup_generator",
    name="ai_module_type",
    create_type=False,
)
_ai_generation_status = PgEnum(
    "pending", "completed", "failed", name="ai_generation_status", create_type=False
)
_ai_job_status = PgEnum(
    "queued",
    "running",
    "succeeded",
    "failed",
    "cancelled",
    name="ai_job_status",
    create_type=False,
)
_ai_job_entity_type = PgEnum(
    "deal", "proposal", "contract", name="ai_job_entity_type", create_type=False
)
_project_status = PgEnum(
    "planning", "active", "on_hold", "completed", name="project_status", create_type=False
)
_task_status = PgEnum(
    "todo", "in_progress", "review", "done", name="task_status", create_type=False
)
_task_priority = PgEnum("low", "medium", "high", name="task_priority", create_type=False)
_task_entity_type = PgEnum(
    "project", "deal", "reminder", name="task_entity_type", create_type=False
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
    # Cutoff for admin-forced session invalidation (suspend, revoke_user_sessions) — any
    # access/refresh token with an `iat` before this is rejected regardless of its own
    # expiry. NULL means no forced revocation has ever happened for this user.
    sessions_revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True, unique=True)

    # Professional profile
    skills: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    specialization: Mapped[str | None] = mapped_column(String(255), nullable=True)
    default_hourly_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="VND")
    portfolio_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Headline hiện trên trang chia sẻ công khai (/intake/{share_token}/profile).
    #
    # Hai cột `service_categories` và `is_listed` từng nằm ở đây để phục vụ danh bạ tìm
    # freelancer. Danh bạ đã bỏ (SoloDesk là CRM riêng của từng người, không phải sàn), nên
    # code thôi map chúng. Cột vẫn còn trong DB: drop cột trong khi container API cũ vẫn
    # đang chạy sẽ làm mọi truy vấn bảng users nổ UndefinedColumn suốt lúc deploy, nên việc
    # drop nằm ở một migration riêng chạy sau khi bản này lên xong.  #Huynh
    professional_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Diện mạo trang công khai, do freelancer tự chọn.
    #
    # `cover_url` chứa data URL base64 (cùng đường với avatar_url) chứ không phải link S3:
    # lớp MinIO có sẵn nhưng dựng URL từ hostname nội bộ Docker nên trình duyệt khách không
    # mở được. `brand_color` là mã hex; frontend ghi đè biến CSS --primary bằng nó nên cả
    # trang đổi màu theo, không phải sửa từng chỗ.  #Huynh
    cover_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    brand_color: Mapped[str | None] = mapped_column(String(9), nullable=True)
    # Địa chỉ riêng dạng /{slug} thay cho link token 43 ký tự. UNIQUE vì là định danh công
    # khai. 32 ký tự là cố ý: token dài hơn thế nên slug không bao giờ đụng token, nhờ vậy
    # MỘT truy vấn tra được cả hai (xem intake_form/infrastructure/repository.py).
    profile_slug: Mapped[str | None] = mapped_column(String(32), nullable=True, unique=True)
    # Nghề chuẩn hoá — slug trong src/modules/intake_form/professions.py. Dùng làm ngữ cảnh cho
    # lead qualifier (chủ deal làm nghề gì). Khác professional_title (headline tự do): đây là MỘT
    # trong N nghề cố định. Nullable = freelancer chưa chọn.  #Huynh
    profession: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Payment info — thư nhắc thanh toán in ra để khách biết chuyển tiền vào đâu.
    #
    # `bank_account_info` (Text tự do) KHÔNG sinh được mã QR: VietQR cần mã ngân hàng và số
    # tài khoản tách rời để dựng chuỗi EMVCo. Nên ba cột có cấu trúc bên dưới mới là nguồn
    # của QR; `bank_account_info` từ nay là ô ghi chú thêm (chi nhánh, lời dặn).  #Huynh
    momo_phone_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    bank_account_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    bank_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    bank_account_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    bank_account_holder: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Mặc định khi soạn lời nhắc — để mỗi lần soạn không phải gõ lại từ đầu.
    reminder_signature: Mapped[str | None] = mapped_column(Text, nullable=True)
    reminder_default_channel: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reminder_default_hour: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

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

    __table_args__ = (Index("idx_password_reset_tokens_user", "user_id", "expires_at"),)


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
    plan: Mapped["PlanModel"] = relationship("PlanModel", foreign_keys=[plan_id])

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
    billing_period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    billing_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ai_generations_used: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

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


class SubscriptionPaymentModel(UUIDMixin, TimestampMixin, Base):
    """A payment intent to upgrade a subscription. `id` doubles as the order
    code handed to the payment provider (e.g. MoMo's `orderId`)."""

    __tablename__ = "subscription_payments"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subscriptions.id"), nullable=False
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subscription_plans.id"), nullable=False
    )
    provider: Mapped[str] = mapped_column(_payment_provider, nullable=False)
    status: Mapped[str] = mapped_column(
        _subscription_payment_status, nullable=False, server_default="pending"
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    pay_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    deeplink: Mapped[str | None] = mapped_column(Text, nullable=True)
    qr_code_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_create_response: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    raw_callback_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("amount >= 0", name="chk_subscription_payments_amount"),
        Index("idx_subscription_payments_user", "user_id"),
        Index("idx_subscription_payments_status", "status"),
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
    # Id của khách trong OA của freelancer (follower id). Lấy từ webhook Zalo khi khách nhắn/
    # follow OA — gửi tin CS phải theo id này, KHÔNG theo số điện thoại. NULL = khách chưa nối
    # Zalo với OA nên chưa gửi CS được.  #Huynh
    zalo_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

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
    desired_timeline: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Ngân sách KHÁCH nêu, ghi lại sau khi freelancer hỏi được — ĐƯỢC chấm điểm.
    #
    # Khác hẳn `estimated_value` ngay bên trên: đó là con số freelancer TỰ ƯỚC để tính doanh
    # thu, và nó bị cấm dùng để chấm điểm (xem `_build_inquiry_context`). Không có cột này
    # thì freelancer gọi điện hỏi được ngân sách xong chẳng có chỗ nào để ghi — biết mình
    # thiếu gì mà vẫn không vá được, luồng đứt ngay đó.  #Huynh
    client_budget: Mapped[str | None] = mapped_column(String(255), nullable=True)
    project_type: Mapped[str | None] = mapped_column(String(200), nullable=True)
    service_category: Mapped[str | None] = mapped_column(String(200), nullable=True)
    pricing_tier: Mapped[str | None] = mapped_column(String(100), nullable=True)
    profession = mapped_column(String(100), nullable=True)
    profession_fields = mapped_column(JSON, nullable=True)
    ai_qualification_score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    ai_qualification_confidence: Mapped[float | None] = mapped_column(nullable=True)
    ai_qualification_recommendation: Mapped[str | None] = mapped_column(
        _ai_recommendation, nullable=True
    )
    ai_qualification_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_qualification_project_type: Mapped[str | None] = mapped_column(String(200), nullable=True)
    ai_qualification_budget_signal: Mapped[str | None] = mapped_column(String(200), nullable=True)
    ai_qualification_timeline_signal: Mapped[str | None] = mapped_column(String(200), nullable=True)
    ai_qualification_urgency_signal: Mapped[str | None] = mapped_column(String(200), nullable=True)
    ai_qualification_red_flags: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    ai_qualification_detected_signals: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    ai_qualification_suggested_actions: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    ai_qualification_next_step: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_qualification_price_range_min: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    ai_qualification_price_range_max: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    document_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    document_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)

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

    # Phiếu này thuộc về deal NÀO.
    #
    # BUG CŨ: bảng này CHỈ có `client_id`. Một khách gửi form hai lần cho hai dự án khác
    # nhau → hai deal, cùng một client. Khi chấm điểm, `get_intake_by_client_id()` trả về
    # phiếu MỚI NHẤT, nên deal cũ bị chấm bằng brief của dự án MỚI.
    #
    # Kiểm chứng thật: khách gửi "Website bán hoa (25 triệu, 20/8)" rồi "App giao hàng
    # (80 triệu, 30/12)" → CẢ HAI deal đều bị AI đọc thành "80 triệu, 30/12".
    #
    # Không chỉ chấm điểm sai: báo giá AI dùng chung hàm đó, nên freelancer gửi cho khách
    # một bản báo giá cho DỰ ÁN SAI.
    #
    # Nullable vì phiếu cũ (tạo trước khi có cột này) không biết thuộc deal nào.  #Huynh
    # Phiếu thuộc về ĐÚNG deal nào. Nullable vì phiếu cũ (trước migration n2b3c4d5e6f7)
    # không biết thuộc deal nào — code phải chịu được NULL và rơi về tra theo client.
    #
    # Có index: tra phiếu theo deal chạy mỗi lần chấm điểm VÀ mỗi lần sinh báo giá.  #Huynh
    deal_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("deals.id", ondelete="CASCADE"),
        nullable=True,
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
        # Tra phiếu theo deal chạy mỗi lần chấm điểm VÀ mỗi lần sinh báo giá. Đặt tên
        # tường minh cho khớp migration n2b3c4d5e6f7 — thiếu dòng này thì metadata lệch
        # DB, và autogenerate đòi XOÁ index ở mọi lần chạy sau.  #Huynh
        Index("idx_deal_intakes_deal", "deal_id"),
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


class IntakeFormConfigModel(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "intake_form_configs"

    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(
        String(500), nullable=False, server_default="Gửi yêu cầu dự án"
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    __table_args__ = (
        UniqueConstraint("owner_user_id", name="uq_intake_form_configs_owner"),
        Index("idx_intake_form_configs_owner", "owner_user_id"),
    )


class IntakeFormFieldModel(UUIDMixin, Base):
    __tablename__ = "intake_form_fields"

    form_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("intake_form_configs.id", ondelete="CASCADE"), nullable=False
    )
    field_key: Mapped[str] = mapped_column(String(100), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    placeholder: Mapped[str | None] = mapped_column(String(500), nullable=True)
    field_type: Mapped[str] = mapped_column(String(50), nullable=False, server_default="text")
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    is_visible: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    __table_args__ = (
        UniqueConstraint("form_id", "field_key", name="uq_intake_form_fields_form_key"),
        Index("idx_intake_form_fields_form", "form_id", "sort_order"),
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

    # --- Bốn cột dưới đây thêm sau: đây là phần CHỨNG MINH của kết quả chấm điểm ---
    #
    # Bảng này vốn đã lưu lịch sử append-only (mỗi lần chấm một dòng) — nhưng chỉ lưu CON SỐ
    # mà vứt phần chứng minh. Bảng "Căn cứ chấm điểm" (5 tiêu chí, điểm từng mục, lý do, dữ
    # kiện trích từ lời khách) chỉ nằm ở **localStorage của trình duyệt**.
    #
    # Hệ quả: đổi máy/xoá cache là deal vẫn hiện "78/100" nhưng KHÔNG còn căn cứ nào — điểm
    # rơi từ trên trời, đúng cái bệnh mà bảng căn cứ sinh ra để chữa. Căn cứ ra quyết định
    # tiền bạc thì không thể để ở chỗ mất lúc nào không hay.
    #
    # Nullable vì các bản ghi CŨ (84 dòng đã có) không có mấy trường này — đọc bản cũ vẫn
    # phải chạy, không được nổ.  #Huynh
    breakdown: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    next_step: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_signals: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # Prompt nào sinh ra bản chấm này. Sửa prompt là đổi hành vi AI — không lưu phiên bản
    # thì không trả lời được "sao deal này 52 mà deal kia 80".  #Huynh
    prompt_version: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # Lúc freelancer bấm "Lưu & chuyển sang Đã đánh giá" — NULL nghĩa là chưa chốt.
    #
    # Bảng này append-only: mỗi lần bấm "Đánh giá" là một dòng, kể cả những lần chấm thử rồi
    # bỏ. Tab "Lịch sử" kể HẾT, đúng vai trò của nó. Nhưng tab "Tài liệu" chỉ được kể bản mà
    # freelancer đã CHỦ ĐỘNG chốt — không thì mỗi lần chấm nghịch lại đẻ thêm một "tài liệu",
    # và tài liệu mất nghĩa. Không có cột này thì hai tab không tài nào phân biệt được.
    #
    # Nullable, và mọi dòng cũ đều NULL: bản chấm trước khi có tính năng này thì đúng là chưa
    # ai chốt cả, đừng đoán hộ.  #Huynh
    saved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Freelancer đã được cảnh báo là bản này chưa đủ 100 điểm, và vẫn chọn chốt.
    #
    # Không có cờ này thì nhìn vào một bản đã chốt 27/100 sẽ không phân biệt được "hệ thống
    # để lọt" với "người dùng biết rõ và tự chịu trách nhiệm". Số điểm thiếu thì suy lại được
    # từ `breakdown`, nhưng việc CÓ ĐƯỢC CẢNH BÁO thì không suy ra từ đâu cả.
    #
    # Dòng cũ để `false`: trước đây không có cảnh báo nào, nên không ai từng chấp nhận gì.
    gap_acknowledged: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    __table_args__ = (
        Index("idx_lead_scores_deal", "deal_id"),
        CheckConstraint("score BETWEEN 0 AND 100", name="ck_lead_scores_score_range"),
        CheckConstraint("confidence BETWEEN 0.0 AND 1.0", name="ck_lead_scores_confidence_range"),
    )


# =============================================================================
# DOMAIN: Proposals
# =============================================================================


class DealAttachmentModel(UUIDMixin, TimestampMixin, Base):
    """File khách gửi kèm deal (brief dự án, yêu cầu kỹ thuật, bảng giá tham khảo...).

    Nghiệp vụ: freelancer đính file PDF của khách vào deal, AI ĐỌC file đó để chấm điểm.

    Đây là mảnh còn thiếu quan trọng: deal tạo tay luôn mất 25 điểm ngân sách vì "khách
    chưa nói gì" — nhưng nếu khách gửi hẳn một file brief thì ĐÓ CHÍNH LÀ LỜI KHÁCH.
    `extracted_text` được đưa vào khối "KHÁCH HÀNG NÓI GÌ" của prompt.

    `extracted_text` lưu sẵn để KHÔNG phải bóc lại PDF mỗi lần chấm điểm — bóc PDF tốn
    CPU, và mỗi deal có thể chấm lại nhiều lần.

    File thật nằm trên object storage (MinIO/S3), DB chỉ giữ `storage_key`. Trước đây
    frontend nhét cả nội dung file dạng base64 vào localStorage — 5MB là vỡ.  #Huynh
    """

    __tablename__ = "deal_attachments"

    deal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("deals.id", ondelete="CASCADE"), nullable=False
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    # Khoá trên object storage. File KHÔNG nằm trong DB.
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)

    # Chữ bóc từ PDF, để AI đọc. NULL = chưa bóc được (PDF scan ảnh, hoặc không phải PDF).
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("idx_deal_attachments_deal", "deal_id"),
        Index("idx_deal_attachments_owner", "owner_user_id"),
    )


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
            "idx_proposals_content_gin",
            "content",
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
            "uq_contracts_one_active_per_deal",
            "deal_id",
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
    subtotal: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default="0")
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, server_default="0")
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default="0")
    total: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default="0")
    amount_paid: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default="0")
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
            "idx_invoices_contract",
            "contract_id",
            postgresql_where=text("contract_id IS NOT NULL"),
        ),
        Index(
            "idx_invoices_deal",
            "deal_id",
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
    status: Mapped[str] = mapped_column(_reminder_status, nullable=False, server_default="pending")
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    message_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Ảnh freelancer chèn vào thư: mã QR chuyển khoản chụp sẵn, ảnh sản phẩm, mockup.
    #
    # Lưu KHOÁ trong kho object storage chứ không lưu bytes: ảnh vài MB nhét vào cột là
    # phình bảng và mọi truy vấn lời nhắc đều nặng theo.
    # Dạng: [{"key": ..., "filename": ..., "content_type": ...}]  #Huynh
    attachments: Mapped[list[dict[str, str]]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    recurrence_rule: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_reminder_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reminders.id"), nullable=True
    )
    retry_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")

    # Lời nhắc do quy tắc tự sinh, đang chờ người duyệt. Nó vẫn ở `pending` — nếu không có
    # cột này thì beat quét thấy và gửi thẳng cho khách, đúng cái người dùng chưa cho phép.
    # `RemindersRepository.list_due()` lọc theo cột này.  #Huynh
    requires_approval: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    # Để giao diện gắn nhãn "Tự động" — người dùng cần phân biệt cái họ tự đặt với cái hệ
    # thống tự sinh, nhất là khi định bấm gửi.
    created_by_rule: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    __table_args__ = (
        CheckConstraint("retry_count BETWEEN 0 AND 3", name="chk_reminders_retry"),
        Index(
            "idx_reminders_owner_status_scheduled",
            "owner_user_id",
            "status",
            "scheduled_at",
        ),
        Index("idx_reminders_target", "target_type", "target_id"),
        Index(
            "idx_reminders_pending_scheduled",
            "scheduled_at",
            postgresql_where=text("status = 'pending'"),
        ),
        Index(
            "idx_reminders_parent",
            "parent_reminder_id",
            postgresql_where=text("parent_reminder_id IS NOT NULL"),
        ),
        # Chống trùng: mỗi lượt quét phải tra "đã có lời nhắc nào cho đúng đối tượng và
        # đúng loại này chưa". Không có index thì quét toàn bảng mỗi ngày.
        Index(
            "idx_reminders_dedup",
            "owner_user_id",
            "target_type",
            "target_id",
            "reminder_type",
            "created_at",
        ),
    )


class ReminderRuleModel(UUIDMixin, TimestampMixin, Base):
    """Quy tắc nhắc tự động của một freelancer.

    Trước đây hệ thống chỉ gửi được lời nhắc do người dùng TỰ TẠO TAY — tức họ vẫn phải nhớ
    hoá đơn nào sắp tới hạn, khách nào im lặng đã lâu. Bảng này để họ khai một lần rồi thôi.

    Mỗi user một bộ 5 quy tắc, sinh lười lần đầu gọi API (xem `ReminderRulesService`) chứ
    KHÔNG backfill trong migration — user đăng ký sau này vẫn có đủ mà không ai phải nhớ
    chạy lại script.  #Huynh
    """

    __tablename__ = "reminder_rules"

    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # Dùng lại `reminder_type_enum` sẵn có — nó đã chứa đúng 5 giá trị cần thiết. Tạo enum
    # mới chỉ để lặp lại y hệt là thêm một thứ nữa phải giữ đồng bộ.
    rule_type: Mapped[str] = mapped_column(_reminder_type_enum, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    # Số ngày TRƯỚC (payment_due) hoặc SAU (các loại còn lại) mốc thời gian của quy tắc.
    offset_days: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    # Chỉ dùng cho quá hạn và tái kết nối — hai loại đáng nhắc lại. NULL = nhắc đúng một lần.
    repeat_every_days: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    channel: Mapped[str] = mapped_column(
        _notification_channel, nullable=False, server_default="in_app"
    )
    # Mặc định FALSE: hệ thống soạn nháp rồi chờ người duyệt. Bật lên là cho phép email
    # khách hàng thật mà không ai đọc lại — phải là hành động có ý thức.
    auto_send: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    # Giờ trong ngày để gửi, theo `users.timezone`. Quét chạy rạng sáng nhưng không ai muốn
    # nhận email công việc lúc 1 giờ sáng.
    send_at_hour: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="9")
    # Nội dung mẫu freelancer tự soạn cho lời nhắc này. NULL = dùng template mặc định trong
    # `RULE_DEFAULTS`. Placeholder `{client_name}`, `{deal_title}`... được thay khi soạn tin.
    message_template: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("owner_user_id", "rule_type", name="uq_reminder_rules_owner_type"),
        CheckConstraint("offset_days BETWEEN 0 AND 365", name="chk_reminder_rules_offset"),
        CheckConstraint(
            "repeat_every_days IS NULL OR repeat_every_days BETWEEN 1 AND 365",
            name="chk_reminder_rules_repeat",
        ),
        CheckConstraint("send_at_hour BETWEEN 0 AND 23", name="chk_reminder_rules_hour"),
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
    total_value: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default="0")
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("owner_user_id", "stage", "snapshot_date", name="uq_pipeline_snapshots"),
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
    # Nghề áp dụng (slug trong intake_form/professions.py). NULL = mẫu dùng chung cho mọi
    # nghề. Đây là chiều "thư viện mẫu theo nghề" Phiếu đòi (Gói 6); cột phẳng + validate
    # qua seam professions, đúng lối đã làm với users.profession.  #Huynh
    profession: Mapped[str | None] = mapped_column(String(64), nullable=True)
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
        # Admin lọc thư viện theo nghề — index để không quét cả bảng.
        Index("idx_system_templates_profession", "profession"),
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
        CheckConstraint("rollout_percentage BETWEEN 0 AND 100", name="chk_feature_flags_rollout"),
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


class AiJobModel(UUIDMixin, TimestampMixin, Base):
    """Tracks a background AI generation run (qualify/proposal/contract) dispatched to Celery.

    Polymorphic binding on entity_type/entity_id — no FK, mirroring TaskModel/
    reminders — since a job can target a deal, proposal, or contract.
    """

    __tablename__ = "ai_jobs"

    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(_ai_module_type, nullable=False)
    entity_type: Mapped[str] = mapped_column(_ai_job_entity_type, nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(_ai_job_status, nullable=False, server_default="queued")
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)

    __table_args__ = (
        Index("idx_ai_jobs_owner", "owner_user_id"),
        Index("idx_ai_jobs_entity", "entity_type", "entity_id"),
        Index(
            "uq_ai_jobs_owner_idempotency_key",
            "owner_user_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
    )

class AIProviderConfigurationModel(Base):
    # Chỉ có MỘT bản ghi trong bảng này, lưu nhà cung cấp LLM đang được toàn hệ
    # thống sử dụng. Admin không thêm/xoá cấu hình mà chỉ cập nhật bản ghi này
    # (Groq ↔ Gemini ↔ OpenAI ↔ ...).  #Trung
    __tablename__ = "ai_provider_configuration"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Nhà cung cấp AI hiện tại của toàn bộ ứng dụng. Model cụ thể của từng nhà
    # cung cấp được hard-code trong codebase để giảm độ phức tạp khi kiểm thử và
    # triển khai.
    llm_provider: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    # Tự động cập nhật mỗi lần admin đổi nhà cung cấp AI.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Admin thực hiện lần thay đổi gần nhất. Dùng SET NULL để vẫn giữ lịch sử cấu
    # hình nếu tài khoản admin bị xoá sau này.
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )


# =============================================================================
# DOMAIN: Projects & Tasks (polymorphic task binding)
# =============================================================================


class ProjectModel(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "projects"

    deal_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("deals.id", ondelete="SET NULL"), nullable=True
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(_project_status, nullable=False, server_default="planning")

    __table_args__ = (
        Index("idx_projects_owner", "owner_id"),
        Index("idx_projects_owner_status", "owner_id", "status"),
        Index("idx_projects_deal", "deal_id"),
    )


class TaskModel(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "tasks"

    # Polymorphic binding — no FK on entity_id (referential integrity enforced
    # at the application layer, mirroring the reminders module).
    entity_type: Mapped[str] = mapped_column(_task_entity_type, nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[str] = mapped_column(_task_priority, nullable=False, server_default="medium")
    status: Mapped[str] = mapped_column(_task_status, nullable=False, server_default="todo")
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Hóa đơn đã xuất cho task này. CHỈ có ý nghĩa với task "Thu tiền:" — mỗi mốc thanh toán
    # một hóa đơn riêng.
    #
    # Vì sao phải là một cột chứ không suy ra được: `invoices` chỉ có `deal_id`, mà một deal
    # có N mốc → N task → N hóa đơn CÙNG `deal_id`. Lịch 50/50 còn cho ra hai hóa đơn SỐ TIỀN
    # BẰNG NHAU, nên cũng không phân biệt được bằng tiền. Không có cột này thì không cách nào
    # biết hóa đơn nào của mốc nào.
    #
    # `ON DELETE SET NULL`: xóa hóa đơn thì task quay về "chưa xuất hóa đơn" và xuất lại được,
    # chứ không kéo theo cả task — task là việc phải làm, hóa đơn chỉ là chứng từ của nó.
    #
    # KHÔNG thêm giá trị vào enum `task_status`: "đã gửi hóa đơn" là trạng thái của HÓA ĐƠN
    # (`draft/sent/partially_paid/paid/void`), suy ra từ đây. Nhét vào `task_status` là làm bẩn
    # trạng thái của mọi task khác trong hệ thống.  #Huynh
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True
    )

    # Số tiền task này phải thu. KHÔNG NULL = đây là task THU TIỀN.
    #
    # Trước đây dấu nhận biết là tiền tố tên `"Thu tiền: "`, và tiền thì tính lại mỗi lần cần
    # bằng cách tra báo giá đã chốt rồi khớp mốc VỚI TÊN TASK. Đổi tên task một chữ là đứt:
    # không xuất được hoá đơn, và bảng doanh thu âm thầm coi mốc đó chưa thu. Một cột thì
    # không đứt được.
    #
    # Chốt số tiền vào đây là ĐÚNG chứ không phải chụp ảnh cẩu thả: lúc sinh task, báo giá
    # đang ở trạng thái `accepted` — trạng thái cuối, `update`/`set_price` đều chặn — nên con
    # số nguồn không thể đổi về sau. Muốn đổi giá thì đi cửa phụ lục hợp đồng.
    #
    # `>= 0` chứ không `> 0`: hạng mục 0 đồng vẫn phải hiện trên bảng việc để freelancer thấy
    # mà sửa, thay vì biến mất im lặng. Chặn 0 đồng là việc của cổng gửi báo giá.  #Huynh
    billing_amount: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)

    # Thu TRƯỚC khi làm hay thu KHI XONG — `on_signing` / `on_completion`, chép từ hạng mục
    # chi phí lúc sinh task (`pdf_content.DUE_TYPE_LABELS`).
    #
    # Không dùng enum Postgres: hai giá trị này là chuyện NGHIỆP VỤ còn đang định hình, mà
    # thêm giá trị vào enum Postgres phải có migration riêng và khoá bảng. `String(20)` +
    # hằng số bên Python đủ chặt cho một thứ chỉ chính code này ghi.
    #
    # NULL với task cũ (trước khi có cột này) và với task freelancer tự thêm.  #Huynh
    billing_due_type: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Thứ tự hiển thị TRONG một entity. Với task thu tiền, đây chính là thứ tự hạng mục chi
    # phí trên tờ báo giá — freelancer kéo sắp lại ở mục 7 thì bảng việc phải theo.
    #
    # Vì sao KHÔNG suy ra được từ `created_at`: `created_at` dùng `server_default=func.now()`,
    # mà `now()` của PostgreSQL trả về thời điểm bắt đầu TRANSACTION. Cả lô task thu tiền sinh
    # trong một transaction nên `created_at` BẰNG NHAU tuyệt đối — `ORDER BY created_at` là
    # hoà hoàn toàn, thứ tự do planner quyết và đổi giữa các lần truy vấn.
    #
    # Tên `position` theo `ChecklistItemModel.position` (anh em gần nhất, cùng module) chứ
    # không theo `sort_order` — cái đó là của các dòng chứng từ tiền (hoá đơn, mốc hợp đồng).
    #
    # NOT NULL + mặc định 0: task tự thêm cũng có thứ tự, không phải xử lý NULL ở mọi chỗ sort.
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    # `selectin` chứ không lazy mặc định: danh sách công việc trả về hàng chục task một lúc,
    # lazy-load là N+1 truy vấn — và trong ngữ cảnh async thì lazy-load còn NỔ hẳn
    # (`MissingGreenlet`) chứ không chỉ chậm.
    invoice: Mapped["InvoiceModel | None"] = relationship("InvoiceModel", lazy="selectin")

    checklist_items: Mapped[list["ChecklistItemModel"]] = relationship(
        "ChecklistItemModel",
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="ChecklistItemModel.position",
        lazy="selectin",
    )

    __table_args__ = (
        Index("idx_tasks_entity", "entity_type", "entity_id"),
        Index("idx_tasks_entity_status", "entity_type", "entity_id", "status"),
        # Phục vụ đúng `list_by_entity` — lọc theo entity rồi sắp theo thứ tự hiển thị.
        Index("idx_tasks_entity_position", "entity_type", "entity_id", "position"),
        # Chỉ mục PHẦN theo ENTITY trước: hai truy vấn dùng nó (guard đóng dự án, bảng doanh
        # thu) đều lọc theo entity rồi mới tới cờ thu tiền. Chỉ mục trần trên `billing_amount`
        # thì không phục vụ được truy vấn nào.
        Index(
            "idx_tasks_billing",
            "entity_type",
            "entity_id",
            postgresql_where=text("billing_amount IS NOT NULL"),
        ),
        CheckConstraint(
            "billing_amount IS NULL OR billing_amount >= 0",
            name="ck_tasks_billing_amount_non_negative",
        ),
    )


class ChecklistItemModel(UUIDMixin, Base):
    __tablename__ = "checklist_items"

    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    is_done: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    task: Mapped["TaskModel"] = relationship("TaskModel", back_populates="checklist_items")

    __table_args__ = (Index("idx_checklist_items_task", "task_id"),)


# Computed counts for ProjectResponse — defined after TaskModel so both tables exist.
# Tasks are polymorphic; a project's tasks are rows where entity_type='project'
# and entity_id == project.id.
ProjectModel.task_count = column_property(
    select(func.count(TaskModel.id))
    .where(TaskModel.entity_type == "project")
    .where(TaskModel.entity_id == ProjectModel.id)
    .correlate_except(TaskModel)
    .scalar_subquery(),
    deferred=False,
)
ProjectModel.done_count = column_property(
    select(func.count(TaskModel.id))
    .where(TaskModel.entity_type == "project")
    .where(TaskModel.entity_id == ProjectModel.id)
    .where(TaskModel.status == "done")
    .correlate_except(TaskModel)
    .scalar_subquery(),
    deferred=False,
)


class NotificationModel(UUIDMixin, TimestampMixin, Base):
    """Thông báo trong ứng dụng cho freelancer (cái chuông trên thanh tiêu đề).

    Vì sao cần: khách gửi Biểu mẫu tiếp nhận → hệ thống tạo deal mới, nhưng freelancer
    KHÔNG hề biết cho tới khi tự mở cột "Deal Mới" ra xem. Deal nóng nằm im vài ngày là
    mất khách — mà cả điểm mạnh của sản phẩm là "AI chấm điểm ngay khi khách gửi form".

    KHÔNG gửi email ở đây. Email là việc của module reminders (có hàng đợi, có retry, có
    ghi nhận gửi thành công/thất bại). Bảng này chỉ là hộp thư trong ứng dụng: rẻ, đọc
    nhanh, không phụ thuộc dịch vụ ngoài.

    `entity_type` + `entity_id` để bấm vào thông báo là nhảy thẳng tới deal/hoá đơn liên
    quan, thay vì bắt người dùng tự đi tìm.  #Huynh
    """

    __tablename__ = "notifications"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)

    entity_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # Truy vấn nóng nhất là "chuông có mấy cái chưa đọc của TÔI" — chạy mỗi lần đổi
        # trang. Index kép user_id + is_read để không phải quét cả bảng.  #Huynh
        Index("idx_notifications_user_unread", "user_id", "is_read"),
        Index("idx_notifications_user_created", "user_id", "created_at"),
    )
