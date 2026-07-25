"""merge heads

Revision ID: e18bf4674da1
Revises: l7g8h9i0j1k2, n9o0p1q2r3s4
Create Date: 2026-07-17 17:57:56.060173
"""

from collections.abc import Sequence

revision: str = 'e18bf4674da1'
down_revision: str | None = ('l7g8h9i0j1k2', 'n9o0p1q2r3s4')
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
