"""add 'sepay' to the payment_provider enum

Revision ID: e5f6a7b8c9d0
Revises: b2c3d4e5f6a7
Create Date: 2026-08-20 00:00:00.000000

Cùng lý do như a1b2c3d4e5f6 đã thêm 'zalopay': `subscription_payments.provider` là ENUM
`payment_provider` của PostgreSQL chứ không phải cột text, nên thêm giá trị ở phía Python
là CHƯA ĐỦ. Thiếu bản này, checkout SePay đi trọn đường — validate qua, dựng xong mã QR —
rồi chết ở đúng câu INSERT đầu tiên với `invalid input value for enum payment_provider`.

PostgreSQL 16 cho phép `ALTER TYPE ... ADD VALUE` bên trong transaction miễn là không DÙNG
giá trị mới trong cùng transaction đó — ở đây không dùng. `IF NOT EXISTS` để chạy lại không vỡ.

Bản này TỪNG mang id `c3d4e5f6a7b8` và phải đổi: nhánh #102 đã có sẵn một revision đúng y
id đó (`c3d4e5f6a7b8_merge_ai_provider_hardening_with_llm_model`), và nó đã merge vào main
nên KHÔNG được đụng tới. Hai file cùng một id khiến alembic không dựng nổi cây revision —
triệu chứng là "Multiple head revisions are present", một câu không hề chỉ tới nguyên nhân
thật. Đổi id ở ĐÂY là an toàn vì bản này chưa merge và chưa deploy: không DB nào từng
stamp nó ngoài mấy DB test cục bộ.

Bài học cho lần sau: đừng đặt id theo dãy đoán được (a1b2..., b2c3..., c3d4...). Hai nhánh
song song sẽ đoán ra cùng một chuỗi. Để `alembic revision` tự sinh id ngẫu nhiên.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: str | Sequence[str] | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE payment_provider ADD VALUE IF NOT EXISTS 'sepay'")


def downgrade() -> None:
    """Không đảo được — xem downgrade của a1b2c3d4e5f6 để biết lý do đầy đủ.

    Tóm tắt: PostgreSQL không có `ALTER TYPE ... DROP VALUE`, và dựng lại type sẽ thất bại
    nếu đã có bản ghi mang giá trị 'sepay' — đúng vào lúc downgrade dễ được gọi nhất.
    Một giá trị enum thừa thì vô hại.
    """
