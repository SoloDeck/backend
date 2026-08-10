import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import UserModel


@dataclass
class UsersRepository:
    db: AsyncSession

    async def get_by_id(self, user_id: uuid.UUID):
        return await self.db.scalar(
            select(UserModel).where(
                UserModel.id == user_id,
                UserModel.deleted_at.is_(None),
            )
        )

    async def get_by_phone(self, phone: str, *, exclude_user_id: uuid.UUID | None = None):
        stmt = select(UserModel).where(
            UserModel.phone == phone,
            UserModel.deleted_at.is_(None),
        )
        if exclude_user_id is not None:
            stmt = stmt.where(UserModel.id != exclude_user_id)
        return await self.db.scalar(stmt)

    async def is_profile_slug_taken(
        self, slug: str, *, exclude_user_id: uuid.UUID | None = None
    ) -> bool:
        """Tên đường dẫn đã có người giữ chưa — kể cả người đã xoá mềm.

        CỐ Ý không lọc `deleted_at IS NULL` như mọi truy vấn khác trong repo này: ràng
        buộc `uq_users_profile_slug` là UNIQUE thường, không phải UNIQUE có điều kiện, nên
        nó đếm cả hàng đã xoá mềm. Lọc ở đây mà DB không lọc thì kiểm tra báo "còn trống",
        `INSERT` xuống lại vỡ ràng buộc → người dùng thấy 500 cho một việc rất bình thường.

        Trả `bool` chứ không trả hàng: nhờ vậy một `UserModel` đã xoá mềm không bao giờ
        thoát ra khỏi repository, phần còn lại của luật "luôn lọc `deleted_at`" vẫn nguyên.

        Muốn bỏ ngoại lệ này thì phải đổi ràng buộc thành UNIQUE có điều kiện bằng một
        migration — sửa mỗi chỗ này là lỗi 500 quay lại.  #Huynh
        """
        stmt = select(UserModel.id).where(UserModel.profile_slug == slug)
        if exclude_user_id is not None:
            stmt = stmt.where(UserModel.id != exclude_user_id)
        return await self.db.scalar(stmt) is not None

    async def save(self, obj):
        await self.db.flush()
        await self.db.refresh(obj)
        return obj
