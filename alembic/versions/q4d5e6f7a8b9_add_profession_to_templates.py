"""add profession to system_templates

Thư viện mẫu điều khoản "theo nhóm nghề" (Phiếu SU26SE083, Gói 6). Cột nullable: mẫu cũ
và mẫu dùng chung để NULL, không cần backfill.  #Huynh

Revision ID: q4d5e6f7a8b9
Revises: p3c4d5e6f7a8
Create Date: 2026-07-24 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "q4d5e6f7a8b9"
down_revision: str | None = "p3c4d5e6f7a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "system_templates",
        sa.Column("profession", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "idx_system_templates_profession", "system_templates", ["profession"]
    )


def downgrade() -> None:
    op.drop_index("idx_system_templates_profession", table_name="system_templates")
    op.drop_column("system_templates", "profession")
