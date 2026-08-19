"""tasks.billing_due_type — thu trước khi làm hay thu khi xong

Revision ID: b5c6d7e8f9a0
Revises: a4b5c6d7e8f9
Create Date: 2026-08-13 22:10:00.000000

Thời điểm thu của một hạng mục vốn là CHỮ TỰ DO, và hệ thống phải đoán xem câu đó có nghĩa
"thu trước" không bằng cách dò từ khoá tiếng Việt. Gõ "Ngay sau khi hai bên xác nhận" là đoán
trượt. Giờ nó là LOẠI có sẵn (`on_signing` / `on_completion`), chép lên task để bảng việc biết
dòng nào đòi được ngay và để cảnh báo khi xuất hoá đơn cho việc chưa làm xong.

Chữ tự do không mất — chuyển sang `due_note` trong báo giá, in đè lên nhãn chuẩn.

BACKFILL: task thu tiền đang có được suy loại từ chính chữ đang lưu ở phần mô tả ("Thời điểm
thu: ..." / "Thời điểm/điều kiện: ..."), dùng đúng bộ từ khoá mà bản cũ dùng. Không suy ra
được thì để NULL — giao diện coi NULL là "chưa rõ" và không cảnh báo gì, thà im còn hơn nhắc sai.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b5c6d7e8f9a0"
down_revision: str | None = "a4b5c6d7e8f9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_ON_SIGNING = "on_signing"
_ON_COMPLETION = "on_completion"

# Đóng băng theo thời gian, không import từ `src` — bộ từ khoá bên đó sẽ còn đổi.
_UPFRONT_HINTS = ("khi ký", "ký hợp đồng", "trước khi", "đặt cọc", "tạm ứng", "ứng trước")


def upgrade() -> None:
    op.add_column("tasks", sa.Column("billing_due_type", sa.String(20), nullable=True))

    bind = op.get_bind()
    rows = (
        bind.execute(
            sa.text(
                "SELECT id, title, description FROM tasks WHERE billing_amount IS NOT NULL"
            )
        )
        .mappings()
        .all()
    )

    updates = []
    for row in rows:
        haystack = f"{row['title'] or ''}\n{row['description'] or ''}".lower()
        if any(hint in haystack for hint in _UPFRONT_HINTS):
            updates.append({"task_id": row["id"], "due_type": _ON_SIGNING})
        elif "hoàn thành" in haystack or "nghiệm thu" in haystack or "bàn giao" in haystack:
            updates.append({"task_id": row["id"], "due_type": _ON_COMPLETION})
        # Không khớp gì → để NULL.

    if updates:
        bind.execute(
            sa.text("UPDATE tasks SET billing_due_type = :due_type WHERE id = :task_id"),
            updates,
        )


def downgrade() -> None:
    op.drop_column("tasks", "billing_due_type")
