"""add message_template to reminder_rules

Cho phép freelancer tự soạn nội dung mẫu cho từng quy tắc nhắc tự động. NULL = dùng
template mặc định trong RULE_DEFAULTS.

Revision ID: s6f7a8b9c0d1
Revises: r5e6f7a8b9c0
Create Date: 2026-07-25 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 's6f7a8b9c0d1'
down_revision: str | None = 'r5e6f7a8b9c0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'reminder_rules',
        sa.Column('message_template', sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('reminder_rules', 'message_template')
