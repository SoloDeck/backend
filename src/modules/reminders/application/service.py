"""Reminders application service."""

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.reminders.infrastructure.repository import RemindersRepository
from src.modules.reminders.schemas.request import ReminderRequest
from src.shared.exceptions.domain import NotFoundError


@dataclass
class RemindersService:
    db: AsyncSession
    repo: RemindersRepository | None = None

    def __post_init__(self) -> None:
        if self.repo is None:
            self.repo = RemindersRepository(self.db)

    async def _get_reminder(self, user_id: uuid.UUID, reminder_id: uuid.UUID):  # type: ignore[return]
        reminder = await self.repo.get_by_id(reminder_id, user_id)
        if reminder is None:
            raise NotFoundError(f"Reminder {reminder_id} not found")
        return reminder

    async def create(self, user_id: uuid.UUID, payload: ReminderRequest):  # type: ignore[return]
        return await self.repo.create(
            owner_user_id=user_id,
            target_type=payload.target_type,
            target_id=payload.target_id,
            reminder_type=payload.reminder_type,
            channel=payload.channel,
            status="pending",
            scheduled_at=payload.scheduled_at,
            message_preview=payload.message_preview,
            attachments=payload.attachments,
        )

    async def list_all(
        self,
        user_id: uuid.UUID,
        status: str | None = None,
        target_type: str | None = None,
    ) -> list:
        return await self.repo.list_all(user_id, status=status, target_type=target_type)

    async def get_one(self, user_id: uuid.UUID, reminder_id: uuid.UUID):  # type: ignore[return]
        return await self._get_reminder(user_id, reminder_id)

    async def update(self, user_id: uuid.UUID, reminder_id: uuid.UUID, payload: ReminderRequest):  # type: ignore[return]
        reminder = await self._get_reminder(user_id, reminder_id)
        reminder.scheduled_at = payload.scheduled_at
        reminder.message_preview = payload.message_preview
        reminder.channel = payload.channel
        reminder.reminder_type = payload.reminder_type
        reminder.attachments = payload.attachments
        return await self.repo.save(reminder)

    async def cancel(self, user_id: uuid.UUID, reminder_id: uuid.UUID) -> None:
        reminder = await self._get_reminder(user_id, reminder_id)
        reminder.status = "cancelled"
        await self.repo.save(reminder)

    async def send_now(self, user_id: uuid.UUID, reminder_id: uuid.UUID):  # type: ignore[return]
        """Gửi ngay, không đợi tới giờ đã hẹn.

        Gửi ĐỒNG BỘ trong request chứ không đẩy vào Celery, vì ba lẽ: dùng lại đúng một
        đường code với worker; trả về kết quả thật ("đã gửi cho ai") thay vì "đã xếp
        hàng" rồi im; và demo được kể cả khi worker chưa bật.  #Huynh
        """
        from src.modules.reminders.application.delivery_service import ReminderDeliveryService

        # Kiểm tra quyền sở hữu TRƯỚC — `ReminderDeliveryService` cố ý không lọc theo
        # người dùng (nó chạy trong ngữ cảnh worker), nên chốt chặn phải nằm ở đây.
        reminder = await self._get_reminder(user_id, reminder_id)
        # `unattended=False`: người dùng vừa bấm nút và đang nhìn màn hình, kết quả trả về
        # ngay trong response. Bắn thêm thông báo vào chuông nữa là nhiễu.
        result = await ReminderDeliveryService(db=self.db).deliver(reminder.id, unattended=False)

        # BẮT BUỘC refresh, không phải cho vui: `updated_at` khai `onupdate=func.now()`
        # nên sau khi gửi xong (có UPDATE) SQLAlchemy đánh dấu cột đó là hết hạn. Pydantic
        # đọc nó ở tầng router — nơi không còn greenlet để chạy truy vấn nạp lười — và nổ
        # `MissingGreenlet`. Nạp sẵn ở đây thì router chỉ việc đọc.  #Huynh
        await self.db.refresh(reminder)
        return reminder, result
