"""add 'sepay' to the payment_provider enum

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-20 00:00:00.000000

Cùng lý do như a1b2c3d4e5f6 đã thêm 'zalopay': `subscription_payments.provider` là ENUM
`payment_provider` của PostgreSQL chứ không phải cột text, nên thêm giá trị ở phía Python
là CHƯA ĐỦ. Thiếu bản này, checkout SePay đi trọn đường — validate qua, dựng xong mã QR —
rồi chết ở đúng câu INSERT đầu tiên với `invalid input value for enum payment_provider`.

PostgreSQL 16 cho phép `ALTER TYPE ... ADD VALUE` bên trong transaction miễn là không DÙNG
giá trị mới trong cùng transaction đó — ở đây không dùng. `IF NOT EXISTS` để chạy lại không vỡ.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c3d4e5f6a7b8"
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
