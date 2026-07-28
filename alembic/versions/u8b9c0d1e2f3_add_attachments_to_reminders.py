"""add attachments to reminders

Freelancer cần chèn ảnh vào thư nhắc: mã QR chuyển khoản chụp sẵn từ app ngân hàng, ảnh
sản phẩm, ảnh mockup. Bảng `reminders` chưa có chỗ nào giữ những thứ đó.

Lưu KHOÁ trong kho object storage (không lưu bytes vào DB): ảnh có thể vài MB, nhét vào cột
là phình bảng và mọi truy vấn lời nhắc đều nặng theo. Mỗi phần tử là
`{"key": ..., "filename": ..., "content_type": ...}`.

Revision ID: u8b9c0d1e2f3
Revises: t7a8b9c0d1e2
Create Date: 2026-07-28 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = 'u8b9c0d1e2f3'
down_revision: str | None = 't7a8b9c0d1e2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'reminders',
        sa.Column(
            'attachments',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default='[]',
        ),
    )


def downgrade() -> None:
    op.drop_column('reminders', 'attachments')
