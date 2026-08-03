"""merge heads

Revision ID: 681ed67b07a0
Revises: 51e81d80cf5c, wacc3446997f
Create Date: 2026-08-03 23:11:43.072280
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '681ed67b07a0'
down_revision: str | None = ('51e81d80cf5c', 'wacc3446997f')
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
