"""add desired_timeline to deals

Revision ID: i4d5e6f7a8b9
Revises: h3c4d5e6f7a8
Create Date: 2026-06-30

"""
import sqlalchemy as sa
from alembic import op

revision = "i4d5e6f7a8b9"
down_revision = "h3c4d5e6f7a8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("deals", sa.Column("desired_timeline", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("deals", "desired_timeline")
