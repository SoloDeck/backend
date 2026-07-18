"""add unique constraint on users phone

Revision ID: f85cb132e701
Revises: k6f7a8b9c0d1
Create Date: 2026-07-02 09:51:14.843520
"""

from collections.abc import Sequence

from alembic import op

revision: str = 'f85cb132e701'
down_revision: str | None = 'k6f7a8b9c0d1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint('uq_users_phone', 'users', ['phone'])


def downgrade() -> None:
    op.drop_constraint('uq_users_phone', 'users', type_='unique')
