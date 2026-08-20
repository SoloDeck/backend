"""merge the payment-gateway chain with main after #102 and #111

Revision ID: f6a7b8c9d0e1
Revises: d4e5f6a7b8c9, e5f6a7b8c9d0
Create Date: 2026-08-20 00:00:00.000000

Hai head, do hai nhánh chạy song song:

- `d4e5f6a7b8c9` — head của main sau khi #102 (admin LLM model) merge vào
- `e5f6a7b8c9d0` — cuối chuỗi thanh toán: a1b2c3d4e5f6 (zalopay) → b2c3d4e5f6a7
  (order_code) → e5f6a7b8c9d0 (sepay)

Thêm nút hợp nhất MỚI chứ không dời `down_revision` của bản nào đang có. Dời cha của một
revision ĐÃ PHÁT HÀNH sẽ khiến mọi DB từng chạy `upgrade head` tưởng mình đang ở head rồi
và LẶNG LẼ bỏ qua các bản nằm giữa — CI không bao giờ bắt được vì CI luôn dựng từ DB rỗng
và đi trọn chuỗi. Chỉ deploy lên dữ liệu thật mới lộ ra.

Không có DDL nào ở đây: hai nhánh đụng vào những bảng khác nhau, nút này chỉ nối cây lại.
"""

from collections.abc import Sequence

revision: str = "f6a7b8c9d0e1"
down_revision: str | Sequence[str] | None = ("d4e5f6a7b8c9", "e5f6a7b8c9d0")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
