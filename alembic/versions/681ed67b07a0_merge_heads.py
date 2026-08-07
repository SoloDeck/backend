"""merge heads

Revision ID: 681ed67b07a0
Revises: v9c0d1e2f3a4, wacc3446997f
Create Date: 2026-08-03 23:11:43.072280

Hợp nhất hai nhánh migration: nhánh main (…-> 51e81d80cf5c -> v9c0d1e2f3a4) và
nhánh của PR #92 (u8b9c0d1e2f3 -> v3736329f982 -> wacc3446997f).

Ban đầu bản này nhận cha là 51e81d80cf5c. Sau khi #97 vào main, main mọc thêm
v9c0d1e2f3a4 CŨNG từ 51e81d80cf5c, nên gộp lại thành hai head và `alembic upgrade
head` từ chối chạy — CI đỏ ngay ở conftest. Nay trỏ sang v9c0d1e2f3a4, tức head
thật hiện tại của main.

Chỉ dời cha ở đúng nút hợp nhất này (upgrade/downgrade đều rỗng, không đụng DDL)
thay vì nối lại v3736329f982 như #97 đã làm: bản đó của #97 chưa lên remote nên
dời cha là sạch, còn wacc3446997f/681ed67b07a0 đã đẩy lên nhánh này rồi.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '681ed67b07a0'
down_revision: str | None = ('v9c0d1e2f3a4', 'wacc3446997f')
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
