"""them cot ly do khong thanh cong cho deals

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-10-03 00:00:00.000000

Deal "khong thanh cong" (giai doan `lost`) tung khong co cach nao vao: nut "Loai bo du an" chi
xoa mem, nen deal mat khoi MOI thong ke va ty le thang luon la 100%. Nay nut do danh dau deal
khong thanh cong va BAT BUOC kem ly do — luu o day de Kho luu tru liet ke duoc "vi sao mat deal".

Cot de trong (NULL) voi moi deal khac va voi deal `lost` cu (neu co); khong backfill vi khong co
ly do nao de bia ra.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e3f4a5b6c7d8"
down_revision: str | Sequence[str] | None = "d2e3f4a5b6c7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("deals", sa.Column("lost_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("deals", "lost_reason")
