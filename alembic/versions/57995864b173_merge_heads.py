"""merge heads

Revision ID: 57995864b173
Revises: 0ff897c5a8db, 654a48c2b861
Create Date: 2026-07-23 13:12:41.276566
"""

from collections.abc import Sequence

revision: str = '57995864b173'
down_revision: str | None = ('0ff897c5a8db', '654a48c2b861')
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
