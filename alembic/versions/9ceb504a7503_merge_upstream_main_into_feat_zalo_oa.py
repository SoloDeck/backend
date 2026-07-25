"""merge upstream main into feat/zalo-oa

Revision ID: 9ceb504a7503
Revises: p1q2r3s4t5u6, s6f7a8b9c0d1
Create Date: 2026-07-25 14:52:13.337654
"""

from collections.abc import Sequence

revision: str = '9ceb504a7503'
down_revision: str | None = ('p1q2r3s4t5u6', 's6f7a8b9c0d1')
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
