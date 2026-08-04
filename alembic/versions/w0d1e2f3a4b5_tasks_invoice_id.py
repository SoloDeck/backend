"""link payment tasks to the invoice issued for them

Revision ID: w0d1e2f3a4b5
Revises: v9c0d1e2f3a4
Create Date: 2026-08-04 15:10:00.000000

Task "Thu tiền:" cần biết ĐÚNG hóa đơn của mốc nó đại diện, để màn Công việc hiện được
"Đã gửi hóa đơn" / "Đã thanh toán" mà không phải đoán.

Không suy ra được từ dữ liệu đang có: `invoices` chỉ có `deal_id`, mà một deal có N mốc →
N task → N hóa đơn CÙNG `deal_id`. Lịch chuẩn 50/50 còn cho ra hai hóa đơn SỐ TIỀN BẰNG
NHAU, nên cũng không phân biệt được bằng tiền.

KHÔNG đụng enum `task_status`: "đã gửi hóa đơn" là trạng thái của HÓA ĐƠN, suy ra từ cột
này. Thêm giá trị vào enum là làm bẩn trạng thái của mọi task khác trong hệ thống.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "w0d1e2f3a4b5"
down_revision: str | None = "v9c0d1e2f3a4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("invoice_id", UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_tasks_invoice_id",
        "tasks",
        "invoices",
        ["invoice_id"],
        ["id"],
        # Xóa hóa đơn thì task quay về "chưa xuất hóa đơn" và xuất lại được, chứ không kéo
        # theo cả task — task là việc phải làm, hóa đơn chỉ là chứng từ của nó.
        ondelete="SET NULL",
    )
    # Chỉ mục PHẦN: đại đa số task không phải task thu tiền nên `invoice_id` là NULL. Đánh
    # chỉ mục cả cột là phí chỗ cho một cột gần như rỗng.
    op.create_index(
        "idx_tasks_invoice_id",
        "tasks",
        ["invoice_id"],
        postgresql_where=sa.text("invoice_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_tasks_invoice_id", table_name="tasks")
    op.drop_constraint("fk_tasks_invoice_id", "tasks", type_="foreignkey")
    op.drop_column("tasks", "invoice_id")
