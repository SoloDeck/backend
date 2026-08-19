"""lead_scores.saved_at — đánh dấu bản đánh giá freelancer đã chốt

Revision ID: x1e2f3a4b5c6
Revises: w0d1e2f3a4b5
Create Date: 2026-08-05

Tab "Lịch sử" kể MỌI lần AI chấm; tab "Tài liệu" chỉ được kể bản đã bấm "Lưu & chuyển sang
Đã đánh giá". Trước đây hai thứ đó không phân biệt được — mỗi lần chấm đều ghi một dòng
`lead_scores` giống hệt nhau, còn nút Lưu chỉ đổi giai đoạn deal.

Nullable và KHÔNG backfill: dòng cũ để NULL vì đúng là chưa ai chốt chúng. Suy ngược
("bản mới nhất coi như đã chốt") là bịa ra một hành động người dùng chưa từng làm.
"""

import sqlalchemy as sa

from alembic import op

revision: str = "x1e2f3a4b5c6"
down_revision: str | None = "w0d1e2f3a4b5"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "lead_scores",
        sa.Column("saved_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Tài liệu chỉ đọc những dòng đã chốt của MỘT deal, sắp theo lúc chốt. Chỉ mục riêng
    # phần khác NULL: phần lớn dòng chưa chốt nên chỉ mục đầy đủ vừa to vừa phí.
    op.create_index(
        "idx_lead_scores_saved",
        "lead_scores",
        ["deal_id", "saved_at"],
        postgresql_where=sa.text("saved_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_lead_scores_saved", table_name="lead_scores")
    op.drop_column("lead_scores", "saved_at")
