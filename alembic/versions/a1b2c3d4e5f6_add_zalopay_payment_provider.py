"""add 'zalopay' to the payment_provider enum

Revision ID: a1b2c3d4e5f6
Revises: f8a9b0c1d2e3
Create Date: 2026-08-20 00:00:00.000000

`subscription_payments.provider` KHÔNG phải cột text — nó là ENUM `payment_provider`
của PostgreSQL (xem `_payment_provider` trong infrastructure/database/models.py, khai
báo với `create_type=False` vì type do migration tạo chứ không do ORM).

Nghĩa là: thêm "zalopay" vào `PaymentProvider` phía Python là CHƯA ĐỦ. Thiếu bản này,
mọi checkout ZaloPay đi trọn đường — validate qua, ký đúng, gọi ZaloPay xong xuôi — rồi
chết ở đúng câu INSERT đầu tiên với `invalid input value for enum payment_provider`.
Test đơn không bắt được (chúng không chạm DB), và cả test tích hợp cũng không, nếu DB
test được dựng từ chuỗi migration này — vì lúc đó nó cũng thiếu y hệt.

PostgreSQL 16 cho phép `ALTER TYPE ... ADD VALUE` bên trong transaction (điều kiện là
không DÙNG giá trị mới trong cùng transaction đó — ở đây ta không dùng), nên bản này
chạy được dưới transaction mà alembic bọc sẵn. `IF NOT EXISTS` để chạy lại không vỡ.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "f8a9b0c1d2e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE payment_provider ADD VALUE IF NOT EXISTS 'zalopay'")


def downgrade() -> None:
    """Không đảo được — và cố đảo thì nguy hiểm hơn là để nguyên.

    PostgreSQL không có `ALTER TYPE ... DROP VALUE`. Cách duy nhất là dựng một type mới
    thiếu 'zalopay', chuyển mọi cột phụ thuộc sang, rồi xoá type cũ — thao tác đó sẽ THẤT
    BẠI giữa chừng nếu đã có dù chỉ một bản ghi thanh toán mang giá trị 'zalopay', tức là
    đúng vào lúc downgrade dễ được gọi nhất (rollback một bản deploy đã chạy thật).

    Để nguyên một giá trị enum thừa thì vô hại: không cột nào bắt buộc phải dùng tới nó.
    Vì vậy đây là no-op có chủ đích, không phải chỗ còn thiếu.
    """
