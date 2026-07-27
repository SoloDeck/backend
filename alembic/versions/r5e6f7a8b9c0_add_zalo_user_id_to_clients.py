"""add zalo_user_id to clients

Id của khách trong OA của freelancer (follower id), lấy từ webhook Zalo. Cần để gửi tin CS
(gửi theo user_id, KHÔNG theo số điện thoại). Nullable: khách cũ / chưa nối Zalo để NULL,
không backfill.  #Huynh

Revision ID: r5e6f7a8b9c0
Revises: q4d5e6f7a8b9
Create Date: 2026-07-24 15:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "r5e6f7a8b9c0"
down_revision: str | None = "q4d5e6f7a8b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "clients",
        sa.Column("zalo_user_id", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("clients", "zalo_user_id")
