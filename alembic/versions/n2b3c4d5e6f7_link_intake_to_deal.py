"""link deal_intakes to a deal

BUG: bảng `deal_intakes` chỉ có `client_id`, không có `deal_id`. Một khách gửi Biểu mẫu
tiếp nhận hai lần cho hai dự án khác nhau → hai deal, cùng một client. Khi chấm điểm,
`get_intake_by_client_id()` trả về phiếu MỚI NHẤT, nên deal cũ bị chấm bằng brief của dự
án MỚI.

Kiểm chứng thật: khách gửi "Website bán hoa (25 triệu, 20/8)" rồi "App giao hàng (80
triệu, 30/12)" → CẢ HAI deal đều bị AI đọc thành "80 triệu, 30/12".

Không chỉ chấm điểm sai: báo giá AI dùng chung hàm đó, nên freelancer gửi cho khách một
bản báo giá cho DỰ ÁN SAI.

Cột nullable vì phiếu cũ không biết thuộc deal nào — code phải chịu được `deal_id IS NULL`
(rơi về tra theo client như cũ).

Revision ID: n2b3c4d5e6f7
Revises: a3430072765c
Create Date: 2026-07-14

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "n2b3c4d5e6f7"
down_revision = "a3430072765c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "deal_intakes",
        sa.Column("deal_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_deal_intakes_deal",
        "deal_intakes",
        "deals",
        ["deal_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("idx_deal_intakes_deal", "deal_intakes", ["deal_id"])


def downgrade() -> None:
    op.drop_index("idx_deal_intakes_deal", table_name="deal_intakes")
    op.drop_constraint("fk_deal_intakes_deal", "deal_intakes", type_="foreignkey")
    op.drop_column("deal_intakes", "deal_id")
