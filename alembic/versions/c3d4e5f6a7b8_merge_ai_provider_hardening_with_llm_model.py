"""merge ai-provider hardening with the configurable-LLM-model branch

Revision ID: c3d4e5f6a7b8
Revises: 6c2f9a1b4d7e, e7f8a9b0c1d2
Create Date: 2026-08-19 00:00:00.000000

6c2f9a1b4d7e (ràng buộc một dòng duy nhất cho ai_provider_configuration) mọc từ
51e81d80cf5c, còn nhánh model cấu hình được đã đi tiếp tới e7f8a9b0c1d2. Hai head.

KHÔNG dời cha của 6c2f9a1b4d7e: bản đó đã đẩy lên nhánh chung, mà đổi cha của một
revision ĐÃ PHÁT HÀNH khiến máy nào từng `upgrade head` coi như đang ở head rồi và
LẶNG LẼ bỏ qua mọi bản nằm giữa. CI không bắt được vì CI luôn dựng từ DB rỗng.

Hai bản này độc lập nhau: một bên thêm cột llm_model, một bên thêm cột is_singleton
cùng CHECK/UNIQUE. Không đụng nhau nên nút hợp nhất để rỗng.
"""

from collections.abc import Sequence

revision: str = "c3d4e5f6a7b8"
down_revision: str | Sequence[str] | None = ("6c2f9a1b4d7e", "e7f8a9b0c1d2")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
