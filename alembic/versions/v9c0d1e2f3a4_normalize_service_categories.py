"""normalize service_categories to directory slugs

Revision ID: v9c0d1e2f3a4
Revises: u8b9c0d1e2f3
Create Date: 2026-08-03 18:40:00.000000

Onboarding từng ghi CHỨC DANH tiếng Anh vào `users.service_categories` ("Web Developer"),
trong khi danh bạ lọc bằng SLUG ("programming"). Hai bộ từ vựng không giao nhau chỗ nào,
nên chọn nhóm dịch vụ nào trên /find-freelancer cũng ra rỗng.

Migration này nắn dữ liệu cũ về slug. Từ nay phía ghi đã có validator chặn (xem
`FreelancerProfileUpdateRequest._valid_service_categories`) nên chuyện này không tái diễn.

KHÔNG đụng cột `specialization`: frontend dùng nó làm cờ "đã xong onboarding"
(`routes/index.tsx`, `routes/onboarding.tsx`), làm nó rỗng là đá mọi user về lại wizard.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "v9c0d1e2f3a4"
down_revision: str | None = "u8b9c0d1e2f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Chức danh cũ -> slug danh bạ. Liệt kê đủ 5 chuyên môn của onboarding dù thực tế chỉ
# 2 giá trị từng được ghi, để migration chạy đúng trên mọi môi trường.
_REMAP: dict[str, str] = {
    "Web Developer": "programming",
    "Brand & Content Designer": "design",
    "Marketing Consultant": "marketing",
    "Photographer / Videographer": "design",
    "Copywriter / SEO": "content",
}


def upgrade() -> None:
    for old, new in _REMAP.items():
        # array_replace đổi đúng phần tử khớp, giữ nguyên các phần tử khác trong mảng —
        # an toàn hơn ghi đè cả mảng nếu sau này một người có nhiều nhóm.
        op.execute(
            f"""
            UPDATE users
            SET service_categories = array_replace(service_categories, '{old}', '{new}')
            WHERE service_categories @> ARRAY['{old}']::text[]
            """
        )

    # Bộ lọc danh bạ dùng `service_categories && ARRAY[...]` mà cột này chưa có chỉ mục
    # nào — đang quét tuần tự toàn bảng users.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_users_service_categories "
        "ON users USING gin (service_categories)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_users_service_categories")
    for old, new in _REMAP.items():
        # Không khôi phục được trung thực: "design" có thể vốn là Designer hoặc
        # Photographer. Trả về giá trị đầu tiên khớp, đủ để rollback chạy.
        op.execute(
            f"""
            UPDATE users
            SET service_categories = array_replace(service_categories, '{new}', '{old}')
            WHERE service_categories @> ARRAY['{new}']::text[]
            """
        )
