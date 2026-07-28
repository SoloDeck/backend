"""add payment info + reminder defaults to users

Thư nhắc thanh toán phải kèm cách trả tiền (Phiếu SU26SE083, dòng 140: "chuỗi nhắc thanh
toán MoMo/chuyển khoản"). Bảng `users` đã có `momo_phone_number` và `bank_account_info`,
nhưng `bank_account_info` là Text tự do nên KHÔNG sinh được mã QR — VietQR cần mã ngân hàng
và số tài khoản tách rời. Thêm ba cột có cấu trúc cho phần chuyển khoản.

Ba cột còn lại là mặc định khi soạn lời nhắc: chữ ký, kênh và giờ gửi ưa thích — để mỗi lần
soạn không phải gõ lại từ đầu.

`bank_account_info` giữ nguyên, từ nay dùng làm ô ghi chú thêm (chi nhánh, lời dặn).

Revision ID: t7a8b9c0d1e2
Revises: 0a57a5cc5e1b
Create Date: 2026-07-28 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 't7a8b9c0d1e2'
# Nối vào bản MERGE `0a57a5cc5e1b`, không nối vào `s6f7a8b9c0d1`: bản merge đó đã gộp
# s6f7... với nhánh payments, nên chọn s6f7... làm cha là đẻ ra head thứ hai và alembic từ
# chối chạy ("Multiple head revisions"). Kiểm bằng `alembic heads` trước khi đặt.  #Huynh
down_revision: str | None = '0a57a5cc5e1b'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- Nhận tiền: đủ để dựng mã VietQR ---
    op.add_column('users', sa.Column('bank_code', sa.String(length=20), nullable=True))
    op.add_column('users', sa.Column('bank_account_number', sa.String(length=50), nullable=True))
    op.add_column('users', sa.Column('bank_account_holder', sa.String(length=255), nullable=True))
    # --- Mặc định khi soạn lời nhắc ---
    op.add_column('users', sa.Column('reminder_signature', sa.Text(), nullable=True))
    op.add_column(
        'users', sa.Column('reminder_default_channel', sa.String(length=20), nullable=True)
    )
    op.add_column('users', sa.Column('reminder_default_hour', sa.SmallInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'reminder_default_hour')
    op.drop_column('users', 'reminder_default_channel')
    op.drop_column('users', 'reminder_signature')
    op.drop_column('users', 'bank_account_holder')
    op.drop_column('users', 'bank_account_number')
    op.drop_column('users', 'bank_code')
