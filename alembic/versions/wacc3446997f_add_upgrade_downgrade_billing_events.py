"""add subscription_upgraded and subscription_downgrade_scheduled to billing_event_type

POST /subscriptions/me/upgrade and /me/downgrade record a billing_events row for
audit purposes, same as every other subscription-mutating action — needs its own
event_type values, same pattern as p1q2r3s4t5u6's subscription_expired addition.

Revision ID: wacc3446997f
Revises: v3736329f982
Create Date: 2026-08-02
"""
from alembic import op

revision = "wacc3446997f"
down_revision = "v3736329f982"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE billing_event_type ADD VALUE IF NOT EXISTS 'subscription_upgraded'")
    op.execute(
        "ALTER TYPE billing_event_type ADD VALUE IF NOT EXISTS 'subscription_downgrade_scheduled'"
    )


def downgrade() -> None:
    # PostgreSQL does not support removing enum values without recreating the type.
    # Downgrade is a no-op; remove manually if needed.
    pass
