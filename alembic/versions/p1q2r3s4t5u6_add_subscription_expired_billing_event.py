"""add subscription_expired to billing_event_type enum

Revision ID: p1q2r3s4t5u6
Revises: 57995864b173
Create Date: 2026-07-23

"""
from alembic import op

revision = "p1q2r3s4t5u6"
down_revision = "57995864b173"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE billing_event_type ADD VALUE IF NOT EXISTS 'subscription_expired'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values without recreating the type.
    # Downgrade is a no-op; remove manually if needed.
    pass
