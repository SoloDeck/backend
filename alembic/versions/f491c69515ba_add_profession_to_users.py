"""add profession to users

Revision ID: f491c69515ba
Revises: 4012c83d6e60
Create Date: 2026-07-21 08:31:01.184457
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f491c69515ba"
down_revision: str | None = "4012c83d6e60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nghề chuẩn hoá của freelancer (slug, 1 trong N nghề cố định). Nullable để hàng cũ vẫn hợp lệ.
    op.add_column("users", sa.Column("profession", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "profession")
