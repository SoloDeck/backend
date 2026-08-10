"""users: ảnh bìa, màu chủ đạo và tên đường dẫn cho trang công khai

Revision ID: y2f3a4b5c6d7
Revises: x1e2f3a4b5c6
Create Date: 2026-08-09

Trang khách hàng mở lên giờ là hồ sơ đầy đủ (bìa + avatar + giới thiệu) rồi mới tới biểu
mẫu, chứ không còn là một cái form trơ. Ba cột này là thứ freelancer tự quyết định về diện
mạo trang đó.

`cover_url` là Text vì ảnh lưu dạng data URL base64 — cùng đường với `avatar_url` đang
dùng. Lớp S3/MinIO có sẵn trong repo nhưng frontend chưa bao giờ gọi, và trên deploy nó
dựng URL từ `STORAGE_ENDPOINT=http://minio:9000` (hostname nội bộ Docker, cổng không
publish) nên trình duyệt khách không mở được. Đi đường base64 là đường đã chứng minh chạy
được cả local lẫn deploy. Độ dài chặn ở tầng schema, không ở đây.

`profile_slug` cho mỗi freelancer một địa chỉ riêng dạng `/{slug}` thay cho token 43 ký tự.
UNIQUE vì nó là định danh công khai. Cố ý để 32 ký tự: `intake_share_token` dài 43+ nên hai
thứ không bao giờ đụng nhau, nhờ vậy một truy vấn tra được cả token lẫn slug.

Cả ba đều nullable và không backfill — tài khoản cũ chưa từng chọn gì thì để trống, giao
diện đã có sẵn trạng thái mặc định tử tế cho từng cột.
"""

import sqlalchemy as sa

from alembic import op

revision: str = "y2f3a4b5c6d7"
down_revision: str | None = "x1e2f3a4b5c6"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("cover_url", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("brand_color", sa.String(length=9), nullable=True))
    op.add_column("users", sa.Column("profile_slug", sa.String(length=32), nullable=True))
    op.create_unique_constraint("uq_users_profile_slug", "users", ["profile_slug"])


def downgrade() -> None:
    op.drop_constraint("uq_users_profile_slug", "users", type_="unique")
    op.drop_column("users", "profile_slug")
    op.drop_column("users", "brand_color")
    op.drop_column("users", "cover_url")
