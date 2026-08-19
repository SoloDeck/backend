"""merge fix/critical-api-bugs with main's task/billing migrations

Revision ID: f8a9b0c1d2e3
Revises: 681ed67b07a0, c6d7e8f9a0b1
Create Date: 2026-08-19 00:00:00.000000

Nhánh này đã có nút hợp nhất 681ed67b07a0 (nối v9c0d1e2f3a4 với wacc3446997f).
Từ đó main mọc thêm w0d1e2f3a4b5 → … → c6d7e8f9a0b1, nên lại thành hai head.

KHÔNG dời cha của 681ed67b07a0 thêm lần nữa. Chính docstring của bản đó ghi là nó
"đã đẩy lên nhánh này rồi" — mà một revision ĐÃ PHÁT HÀNH thì máy nào từng chạy
`upgrade head` cũng đang ghi đúng id đó trong alembic_version. Dời cha khiến alembic
thấy "đang ở head rồi" và LẶNG LẼ bỏ qua mọi bản nằm giữa; CI không bao giờ bắt được
vì CI luôn dựng từ DB rỗng và đi hết chuỗi.

Thêm nút hợp nhất mới là cách an toàn cho cả hai phía: DB đang ở 681ed67b07a0 sẽ chạy
tiếp bốn bản của main rồi tới đây, còn DB trống thì đi trọn chuỗi như thường.
"""

from collections.abc import Sequence

revision: str = "f8a9b0c1d2e3"
down_revision: str | Sequence[str] | None = ("681ed67b07a0", "c6d7e8f9a0b1")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
