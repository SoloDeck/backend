"""add intake_share_token to users

Revision ID: g2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-06-14 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'g2b3c4d5e6f7'
down_revision: str | None = 'f1a2b3c4d5e6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('users', sa.Column('intake_share_token', sa.String(length=64), nullable=True))
    op.create_unique_constraint('uq_users_intake_share_token', 'users', ['intake_share_token'])


def downgrade() -> None:
    op.drop_constraint('uq_users_intake_share_token', 'users', type_='unique')
    op.drop_column('users', 'intake_share_token')
