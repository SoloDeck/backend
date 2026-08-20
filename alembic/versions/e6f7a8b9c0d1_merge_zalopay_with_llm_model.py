"""merge feat/zalopay-payment-adapter with main's llm-model migrations

Revision ID: e6f7a8b9c0d1
Revises: a1b2c3d4e5f6, d4e5f6a7b8c9
Create Date: 2026-08-20 00:00:00.000000

a1b2c3d4e5f6 (thêm 'zalopay' vào enum payment_provider) và d4e5f6a7b8c9 (merge
llm-model với main) rẽ nhánh từ cùng cha f8a9b0c1d2e3 và không có nút hợp nhất nào
nối lại — CI của mọi PR sau đó đều fail ngay ở bước dựng DB test với
"Multiple head revisions are present for given argument 'head'".

Nút hợp nhất mới, không đổi cha của hai bản trên (giữ nguyên vì cả hai đã phát
hành — xem lý do trong f8a9b0c1d2e3).
"""

from collections.abc import Sequence

revision: str = "e6f7a8b9c0d1"
down_revision: str | Sequence[str] | None = ("a1b2c3d4e5f6", "d4e5f6a7b8c9")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
