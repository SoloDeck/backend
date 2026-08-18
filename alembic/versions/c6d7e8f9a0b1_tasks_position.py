"""tasks.position — thứ tự hiển thị trong một entity

Revision ID: c6d7e8f9a0b1
Revises: b5c6d7e8f9a0
Create Date: 2026-08-17 14:20:00.000000

Bảng việc vốn sắp theo `created_at DESC` trần. Với task THU TIỀN thì đó là sắp xếp HOÀ HOÀN
TOÀN: cả lô sinh trong một transaction, mà `now()` của PostgreSQL trả về thời điểm bắt đầu
transaction, nên mọi dòng có `created_at` bằng nhau tới từng micro giây. Thứ tự thực tế do
planner quyết và đổi giữa các lần truy vấn — cùng một dự án, F5 hai lần ra hai thứ tự.

Chuyện này thành hẳn lỗi nghiệp vụ từ khi freelancer kéo sắp lại được các hạng mục chi phí ở
mục 7 của báo giá: sắp cho đúng trình tự triển khai (thiết kế → phát triển → bàn giao) rồi mở
bảng việc ra vẫn thấy lộn xộn.

BACKFILL: đánh số lại TOÀN BỘ task theo `(created_at, id)` trong từng entity. Thứ tự gốc của
các lô cũ đã mất thật — `created_at` bằng nhau thì không có gì để khôi phục. Mục tiêu ở đây
chỉ là ỔN ĐỊNH: từ nay mỗi entity có một thứ tự cố định, không đổi giữa các lần truy vấn.
Deal tạo sau khi có bản này mới mang đúng thứ tự hạng mục trên báo giá.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c6d7e8f9a0b1"
down_revision: str | None = "b5c6d7e8f9a0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
    )

    # `id` là khoá chót để kết quả tất định ngay cả khi `created_at` bằng nhau — chính là
    # tình huống của mọi lô task thu tiền.
    op.execute(
        """
        WITH ordered AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY entity_type, entity_id
                       ORDER BY created_at, id
                   ) - 1 AS rn
            FROM tasks
        )
        UPDATE tasks t
        SET position = ordered.rn
        FROM ordered
        WHERE ordered.id = t.id
        """
    )

    op.create_index(
        "idx_tasks_entity_position",
        "tasks",
        ["entity_type", "entity_id", "position"],
    )


def downgrade() -> None:
    op.drop_index("idx_tasks_entity_position", table_name="tasks")
    op.drop_column("tasks", "position")
