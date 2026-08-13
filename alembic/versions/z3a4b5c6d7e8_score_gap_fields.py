"""deals.client_budget + lead_scores.gap_acknowledged — nối lại vòng bổ sung–chấm lại

Revision ID: z3a4b5c6d7e8
Revises: y2f3a4b5c6d7
Create Date: 2026-08-13

Hai cột phục vụ cùng một việc: bảng chấm điểm giờ nói được freelancer THIẾU gì và cần LÀM gì,
nhưng làm xong thì phải có chỗ để ghi và có dấu vết khi chốt thiếu điểm.

``deals.client_budget`` — ngân sách KHÁCH nêu, freelancer ghi lại sau khi hỏi được. Trước đây
không có ô nào cho nó: `estimated_value` là con số freelancer tự ước và bị CẤM chấm điểm, còn
`deal_intakes.estimated_budget` thì chỉ khách tự điền qua biểu mẫu mới có. Hỏi qua điện thoại
xong không biết ghi vào đâu — biết mình thiếu gì mà vẫn không vá được.

``lead_scores.gap_acknowledged`` — freelancer đã được cảnh báo bản này chưa đủ 100 điểm và vẫn
chọn chốt. Số điểm thiếu suy lại được từ `breakdown`, nhưng việc CÓ ĐƯỢC CẢNH BÁO thì không
suy ra từ đâu cả.

Cả hai đều thêm mới, không đụng dữ liệu cũ. Dòng cũ mặc định `false` vì trước đây không có
cảnh báo nào để mà chấp nhận.
"""

import sqlalchemy as sa

from alembic import op

revision: str = "z3a4b5c6d7e8"
down_revision: str | None = "y2f3a4b5c6d7"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("deals", sa.Column("client_budget", sa.String(length=255), nullable=True))
    op.add_column(
        "lead_scores",
        sa.Column(
            "gap_acknowledged",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("lead_scores", "gap_acknowledged")
    op.drop_column("deals", "client_budget")
