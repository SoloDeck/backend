"""merge the SePay chain with main's head

Revision ID: ce3d449626e9
Revises: e6f7a8b9c0d1, e5f6a7b8c9d0
Create Date: 2026-08-20 00:00:00.000000

Hai head sau khi kéo main về:

- `e6f7a8b9c0d1` — head của main, do #116 dựng để nối `a1b2c3d4e5f6` (enum zalopay)
  với `d4e5f6a7b8c9` (llm-model). Bản đó ĐÃ nằm trên main, KHÔNG đụng vào.
- `e5f6a7b8c9d0` — cuối chuỗi SePay: a1b2c3d4e5f6 → b2c3d4e5f6a7 → e5f6a7b8c9d0

Nhánh này từng có một nút hợp nhất riêng (`f6a7b8c9d0e1`) nối `d4e5f6a7b8c9` với chuỗi
SePay. #116 giải quyết cùng chỗ chạc đó theo cách khác và đã lên main trước, nên giữ cả
hai là để lại đúng hai head. Bản của main được giữ; bản của nhánh này bị xoá và thay bằng
đúng một nút nối head của main với chuỗi SePay.

Xoá được `f6a7b8c9d0e1` vì nó chưa bao giờ merge hay deploy — không DB nào ngoài mấy DB
test cục bộ từng stamp nó. Với một revision đã phát hành thì KHÔNG làm vậy: khi đó phải
thêm nút mới chứ không sửa hay xoá bản cũ.

Id lấy ngẫu nhiên chứ không nối tiếp dãy đoán được. Chính lối đặt id theo dãy
(a1b2..., b2c3..., c3d4...) đã khiến migration SePay đụng nguyên id với một bản của #102
và alembic báo thành "Multiple head revisions are present" — một câu không chỉ tới nguyên
nhân thật.

Không có DDL: hai nhánh đụng những bảng khác nhau, nút này chỉ nối cây lại.
"""

from collections.abc import Sequence

revision: str = "ce3d449626e9"
down_revision: str | Sequence[str] | None = ("e6f7a8b9c0d1", "e5f6a7b8c9d0")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
