"""add reminder_rules table and approval flags on reminders

Quy tắc nhắc tự động: hệ thống tự phát hiện hoá đơn sắp tới hạn, báo giá khách chưa
phản hồi, hợp đồng chờ ký... rồi soạn sẵn lời nhắc.

`reminder_rules` KHÔNG được backfill ở đây — mỗi user tự sinh 5 quy tắc mặc định lần
đầu gọi `GET /reminders/rules`. Backfill trong migration thì user đăng ký ngày mai lại
không có quy tắc nào, mà chẳng ai nhớ ra để chạy lại.  #Huynh

Revision ID: p3c4d5e6f7a8
Revises: f491c69515ba
Create Date: 2026-07-23 15:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "p3c4d5e6f7a8"
down_revision: str | None = "f491c69515ba"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# create_type=False: hai enum này đã tồn tại trong database từ migration đầu tiên. Để
# SQLAlchemy tự tạo thì nó ném "type already exists" và migration vỡ giữa chừng.
_reminder_type_enum = postgresql.ENUM(
    "follow_up",
    "proposal_follow_up",
    "contract_signing_nudge",
    "payment_due",
    "payment_overdue",
    "re_engagement",
    "custom",
    name="reminder_type_enum",
    create_type=False,
)
_notification_channel = postgresql.ENUM(
    "email", "in_app", "both", "zalo", name="notification_channel", create_type=False
)


def upgrade() -> None:
    op.create_table(
        "reminder_rules",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "owner_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rule_type", _reminder_type_enum, nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("offset_days", sa.SmallInteger(), nullable=False),
        sa.Column("repeat_every_days", sa.SmallInteger(), nullable=True),
        sa.Column("channel", _notification_channel, nullable=False, server_default="in_app"),
        sa.Column("auto_send", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("send_at_hour", sa.SmallInteger(), nullable=False, server_default="9"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("owner_user_id", "rule_type", name="uq_reminder_rules_owner_type"),
        sa.CheckConstraint("offset_days BETWEEN 0 AND 365", name="chk_reminder_rules_offset"),
        sa.CheckConstraint(
            "repeat_every_days IS NULL OR repeat_every_days BETWEEN 1 AND 365",
            name="chk_reminder_rules_repeat",
        ),
        sa.CheckConstraint("send_at_hour BETWEEN 0 AND 23", name="chk_reminder_rules_hour"),
    )

    # Lời nhắc chờ duyệt vẫn ở `pending`. Không có cột này thì beat quét thấy và gửi thẳng
    # cho khách — đúng cái người dùng chưa cho phép.
    op.add_column(
        "reminders",
        sa.Column(
            "requires_approval", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.add_column(
        "reminders",
        sa.Column("created_by_rule", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    # Mỗi lượt quét đều hỏi "đã có lời nhắc cho đúng đối tượng và đúng loại này chưa".
    # Không có index thì quét toàn bảng `reminders` mỗi ngày.
    op.create_index(
        "idx_reminders_dedup",
        "reminders",
        ["owner_user_id", "target_type", "target_id", "reminder_type", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_reminders_dedup", table_name="reminders")
    op.drop_column("reminders", "created_by_rule")
    op.drop_column("reminders", "requires_approval")
    op.drop_table("reminder_rules")
