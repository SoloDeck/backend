"""merge heads

Revision ID: 654a48c2b861
Revises: l7g8h9i0j1k2, n9i0j1k2l3m4
Create Date: 2026-07-18 18:41:03.926553
"""

from collections.abc import Sequence

revision: str = '654a48c2b861'
down_revision: str | None = ('l7g8h9i0j1k2', 'n9i0j1k2l3m4')
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
