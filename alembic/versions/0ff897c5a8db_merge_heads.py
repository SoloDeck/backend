"""merge heads

Revision ID: 0ff897c5a8db
Revises: e18bf4674da1, n9i0j1k2l3m4
Create Date: 2026-07-18 18:14:02.944480
"""

from collections.abc import Sequence

revision: str = '0ff897c5a8db'
down_revision: str | None = ('e18bf4674da1', 'n9i0j1k2l3m4')
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
