"""merge main #82 (payments/deploy) with crm heads

Revision ID: 0a57a5cc5e1b
Revises: p1q2r3s4t5u6, s6f7a8b9c0d1
Create Date: 2026-07-27 11:29:37.236088
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0a57a5cc5e1b'
down_revision: str | None = ('p1q2r3s4t5u6', 's6f7a8b9c0d1')
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
