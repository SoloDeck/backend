"""merge_projects_and_desired_timeline_heads

Revision ID: 3a951df6b338
Revises: a0b1c2d3e4f5, i4d5e6f7a8b9
Create Date: 2026-06-30 19:47:11.047148
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '3a951df6b338'
down_revision: str | None = ('a0b1c2d3e4f5', 'i4d5e6f7a8b9')
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
