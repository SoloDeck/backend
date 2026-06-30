"""add ai qualification rich fields to deals

Revision ID: j5e6f7a8b9c0
Revises: i4d5e6f7a8b9
Create Date: 2026-06-30

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "j5e6f7a8b9c0"
down_revision = "i4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("deals", sa.Column("ai_qualification_next_step", sa.Text(), nullable=True))
    op.add_column("deals", sa.Column("ai_qualification_detected_signals", JSONB(), nullable=True))
    op.add_column("deals", sa.Column("ai_qualification_suggested_actions", JSONB(), nullable=True))
    op.add_column("deals", sa.Column("ai_qualification_price_range_min", sa.BigInteger(), nullable=True))
    op.add_column("deals", sa.Column("ai_qualification_price_range_max", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("deals", "ai_qualification_price_range_max")
    op.drop_column("deals", "ai_qualification_price_range_min")
    op.drop_column("deals", "ai_qualification_suggested_actions")
    op.drop_column("deals", "ai_qualification_detected_signals")
    op.drop_column("deals", "ai_qualification_next_step")
