"""Truy vấn bảng `notifications`."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import NotificationModel


class NotificationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        type: str,
        title: str,
        body: str | None,
        entity_type: str | None,
        entity_id: uuid.UUID | None,
    ) -> NotificationModel:
        row = NotificationModel(
            user_id=user_id,
            type=type,
            title=title,
            body=body,
            entity_type=entity_type,
            entity_id=entity_id,
            is_read=False,
        )
        self.db.add(row)
        await self.db.flush()
        return row

    async def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        unread_only: bool = False,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[NotificationModel], int]:
        where = [NotificationModel.user_id == user_id]
        if unread_only:
            where.append(NotificationModel.is_read.is_(False))

        total = await self.db.scalar(
            select(func.count()).select_from(NotificationModel).where(*where)
        )
        rows = await self.db.scalars(
            select(NotificationModel)
            .where(*where)
            .order_by(NotificationModel.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows), int(total or 0)

    async def count_unread(self, user_id: uuid.UUID) -> int:
        total = await self.db.scalar(
            select(func.count())
            .select_from(NotificationModel)
            .where(
                NotificationModel.user_id == user_id,
                NotificationModel.is_read.is_(False),
            )
        )
        return int(total or 0)

    async def mark_read(self, user_id: uuid.UUID, notification_id: uuid.UUID) -> bool:
        """Trả về False nếu thông báo không tồn tại HOẶC không phải của người này.

        Lọc theo `user_id` ngay trong WHERE, không tra ra rồi mới so chủ sở hữu: quên một
        lần so là người khác đánh dấu đã đọc thông báo của mình.  #Huynh
        """
        result = await self.db.execute(
            update(NotificationModel)
            .where(
                NotificationModel.id == notification_id,
                NotificationModel.user_id == user_id,
                NotificationModel.is_read.is_(False),
            )
            .values(is_read=True, read_at=datetime.now(UTC))
        )
        return (result.rowcount or 0) > 0

    async def mark_all_read(self, user_id: uuid.UUID) -> int:
        result = await self.db.execute(
            update(NotificationModel)
            .where(
                NotificationModel.user_id == user_id,
                NotificationModel.is_read.is_(False),
            )
            .values(is_read=True, read_at=datetime.now(UTC))
        )
        return result.rowcount or 0
