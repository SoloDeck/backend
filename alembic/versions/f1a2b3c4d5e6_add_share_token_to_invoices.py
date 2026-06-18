"""add share_token to invoices

Revision ID: f1a2b3c4d5e6
Revises: e59ec510b7af
Create Date: 2026-06-14 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'f1a2b3c4d5e6'
down_revision: str | None = 'e59ec510b7af'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('invoices', sa.Column('share_token', sa.String(length=128), nullable=True))
    op.create_unique_constraint('uq_invoices_share_token', 'invoices', ['share_token'])
    op.create_index('idx_invoices_share_token', 'invoices', ['share_token'])


def downgrade() -> None:
    op.drop_index('idx_invoices_share_token', table_name='invoices')
    op.drop_constraint('uq_invoices_share_token', 'invoices', type_='unique')
    op.drop_column('invoices', 'share_token')
