"""add profession qualification fields to deals

Revision ID: m8h9i0j1k2l3
Revises: k6f7a8b9c0d1
Create Date: 2026-07-13

"""
import sqlalchemy as sa
from alembic import op

revision = "m8h9i0j1k2l3"
down_revision = "k6f7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("deals", sa.Column("profession", sa.String(length=100), nullable=True))
    op.add_column("deals", sa.Column("profession_fields", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("deals", "profession_fields")
    op.drop_column("deals", "profession")