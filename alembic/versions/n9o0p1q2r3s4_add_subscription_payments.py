"""add subscription_payments table

Revision ID: n9o0p1q2r3s4
Revises: m8h9i0j1k2l3
Create Date: 2026-07-17

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "n9o0p1q2r3s4"
down_revision = "m8h9i0j1k2l3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE TYPE payment_provider AS ENUM ('momo', 'bank_transfer', 'vnpay', 'manual')")
    op.execute(
        "CREATE TYPE subscription_payment_status AS ENUM "
        "('pending', 'processing', 'succeeded', 'failed', 'expired', 'cancelled')"
    )
    op.create_table(
        "subscription_payments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subscription_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "provider",
            postgresql.ENUM(name="payment_provider", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(name="subscription_payment_status", create_type=False),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("pay_url", sa.Text(), nullable=True),
        sa.Column("deeplink", sa.Text(), nullable=True),
        sa.Column("qr_code_url", sa.Text(), nullable=True),
        sa.Column("provider_reference", sa.String(length=255), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("raw_create_response", postgresql.JSONB(), nullable=True),
        sa.Column("raw_callback_payload", postgresql.JSONB(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscriptions.id"]),
        sa.ForeignKeyConstraint(["plan_id"], ["subscription_plans.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("amount >= 0", name="chk_subscription_payments_amount"),
    )
    op.create_index(
        "idx_subscription_payments_user", "subscription_payments", ["user_id"], unique=False
    )
    op.create_index(
        "idx_subscription_payments_status", "subscription_payments", ["status"], unique=False
    )


def downgrade() -> None:
    op.drop_index("idx_subscription_payments_status", table_name="subscription_payments")
    op.drop_index("idx_subscription_payments_user", table_name="subscription_payments")
    op.drop_table("subscription_payments")
    op.execute("DROP TYPE subscription_payment_status")
    op.execute("DROP TYPE payment_provider")
