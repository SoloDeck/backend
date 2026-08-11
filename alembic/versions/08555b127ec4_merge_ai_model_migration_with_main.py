"""merge AI model migration with main

Revision ID: 08555b127ec4
Revises: d102d3bcbd01, y2f3a4b5c6d7
Create Date: 2026-08-11 19:54:17.948561
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '08555b127ec4'
down_revision: str | None = ('d102d3bcbd01', 'y2f3a4b5c6d7')
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
