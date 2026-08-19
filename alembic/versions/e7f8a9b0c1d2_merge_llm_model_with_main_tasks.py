"""merge LLM model branch with main's task/billing migrations

Revision ID: e7f8a9b0c1d2
Revises: 08555b127ec4, c6d7e8f9a0b1
Create Date: 2026-08-19 00:00:00.000000

Nhánh `feat/admin-llm-model-management` đã có sẵn một mốc hợp nhất (08555b127ec4) nối
d102d3bcbd01 với head của main lúc đó là y2f3a4b5c6d7. Từ đó main chạy tiếp bốn bản nữa
(z3a4b5c6d7e8 → a4b5c6d7e8f9 → b5c6d7e8f9a0 → c6d7e8f9a0b1), nên sau khi merge main vào
nhánh này lại có HAI head.

KHÔNG sửa down_revision của 08555b127ec4 để trỏ thẳng sang c6d7e8f9a0b1: bản đó đã được
đẩy lên nhánh chung từ commit b6dde73, nên máy nào đã `upgrade head` một lần thì bảng
alembic_version đang ghi đúng id đó. Đổi cha của một revision ĐÃ PHÁT HÀNH khiến alembic
thấy "đang ở head rồi" và LẶNG LẼ bỏ qua cả bốn bản mới của main — cột deals.client_budget
không bao giờ được tạo, và lỗi chỉ nổ ra lúc chạy chứ không phải lúc migrate.

Thêm một mốc hợp nhất mới là cách an toàn: máy đang ở 08555b127ec4 sẽ chạy tiếp bốn bản
của main rồi tới đây, còn DB trống thì chạy toàn bộ như thường.
"""

from collections.abc import Sequence

revision: str = "e7f8a9b0c1d2"
down_revision: str | Sequence[str] | None = ("08555b127ec4", "c6d7e8f9a0b1")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
