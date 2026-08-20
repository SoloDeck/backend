"""add subscription_payments.order_code (short, unique, human-typeable)

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-20 00:00:00.000000

Mã đơn ngắn dạng `SD7K2M9P` để đặt vào nội dung chuyển khoản. `subscription_payments.id`
(UUID) vẫn là mã đơn cho MoMo/ZaloPay — cột này phục vụ cổng kiểu đối soát ngân hàng,
nơi thứ duy nhất nối ta với một khoản tiền vào là dòng nội dung chuyển khoản.

NULLABLE, và có chủ đích:

Mọi bản ghi thanh toán tạo trước bản vá này không có mã, và KHÔNG có cách nào bịa ra một
mã đúng cho chúng. Postgres cho phép nhiều NULL cùng tồn tại trong một unique index, nên
cột này vừa nullable vừa unique mà không mâu thuẫn.

Đây cũng là lý do KHÔNG có bước backfill nào ở đây. Một backfill sai trước
`ALTER ... SET NOT NULL` luôn xanh trên CI — CI dựng DB từ rỗng nên không có hàng nào để
backfill sai — và chỉ chết lúc deploy lên dữ liệu thật. Không cần NOT NULL thì đừng tạo
ra cơ hội đó.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "subscription_payments",
        sa.Column("order_code", sa.String(length=16), nullable=True),
    )
    # Unique index chứ không phải UniqueConstraint: đây là chốt chặn thật cho việc hai đơn
    # mang cùng một mã (xem `generate_order_code` — không có vòng thử lại nào ở tầng ứng
    # dụng, unique index CHÍNH LÀ cơ chế đảm bảo).
    op.create_index(
        "uq_subscription_payments_order_code",
        "subscription_payments",
        ["order_code"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_subscription_payments_order_code", table_name="subscription_payments")
    op.drop_column("subscription_payments", "order_code")
