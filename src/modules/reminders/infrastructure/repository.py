import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import (
    ClientModel,
    ContractModel,
    DealModel,
    InvoiceModel,
    ReminderDeliveryRecordModel,
    ReminderModel,
    UserModel,
)

# Reminder đang chờ Celery thử lại vẫn nằm ở `pending`. Không chừa nó ra thì mỗi phút
# beat lại xếp thêm một lượt gửi chồng lên lượt đang retry → khách nhận email trùng.  #Huynh
RETRY_BACKOFF = timedelta(minutes=10)


@dataclass
class RemindersRepository:
    db: AsyncSession

    async def get_by_id(self, reminder_id: uuid.UUID, owner_user_id: uuid.UUID):
        return await self.db.scalar(
            select(ReminderModel).where(
                ReminderModel.id == reminder_id,
                ReminderModel.owner_user_id == owner_user_id,
            )
        )

    async def get_for_delivery(self, reminder_id: uuid.UUID) -> ReminderModel | None:
        """Đọc reminder kèm KHOÁ HÀNG, dùng cho khâu gửi.

        Không lọc theo `owner_user_id`: worker chạy nền, không có ai đăng nhập.

        `with_for_update()` là thứ chặn gửi trùng: hai lượt gửi cùng một reminder thì
        lượt sau bị khoá chặn lại, tỉnh dậy đã thấy status='sent' và bỏ qua. Nhờ vậy
        không phải thêm trạng thái 'queued' vào enum (kéo theo migration + sửa cả
        frontend lẫn openapi).  #Huynh
        """
        reminder: ReminderModel | None = await self.db.scalar(
            select(ReminderModel).where(ReminderModel.id == reminder_id).with_for_update()
        )
        return reminder

    async def list_due(self, *, limit: int = 200) -> list[ReminderModel]:
        """Các reminder tới giờ phải gửi, bỏ qua hàng đang bị lượt khác giữ."""
        now = datetime.now(UTC)
        result = await self.db.execute(
            select(ReminderModel)
            .where(
                ReminderModel.status == "pending",
                ReminderModel.scheduled_at <= now,
                # Vừa thử hỏng cách đây chưa lâu → để Celery retry lo, đừng xếp thêm.
                (ReminderModel.retry_count == 0)
                | (ReminderModel.updated_at <= now - RETRY_BACKOFF),
            )
            .order_by(ReminderModel.scheduled_at)
            # Beat chạy 60 giây một lần — một cú tick không được ôm nguyên bảng.
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list(result.scalars().all())

    async def get_owner(self, owner_user_id: uuid.UUID) -> UserModel | None:
        result: UserModel | None = await self.db.scalar(
            select(UserModel).where(UserModel.id == owner_user_id)
        )
        return result

    async def resolve_target(
        self,
        *,
        target_type: str,
        target_id: uuid.UUID,
        owner_user_id: uuid.UUID,
    ) -> tuple[ClientModel | None, str | None]:
        """Từ đối tượng được nhắc, tìm ra KHÁCH nhận thư và MỘT NHÃN để đặt tiêu đề.

        Ánh xạ giống hệt `FollowUpService._load_context` — cùng một quan niệm "nhắc về
        cái gì thì gửi cho khách của cái đó".
        """
        if target_type == "client":
            client = await self._owned(ClientModel, target_id, owner_user_id)
            return client, (client.name if client else None)

        if target_type == "deal":
            deal = await self._owned(DealModel, target_id, owner_user_id)
            if deal is None:
                return None, None
            return await self._client(deal.client_id, owner_user_id), deal.title

        if target_type == "invoice":
            invoice = await self._owned(InvoiceModel, target_id, owner_user_id)
            if invoice is None:
                return None, None
            return await self._client(invoice.client_id, owner_user_id), invoice.invoice_number

        if target_type == "contract":
            contract = await self._owned(ContractModel, target_id, owner_user_id)
            if contract is None:
                return None, None
            # Hợp đồng không có cột tiêu đề — lấy tên dự án của deal nó thuộc về.
            deal = await self._owned(DealModel, contract.deal_id, owner_user_id)
            return await self._client(contract.client_id, owner_user_id), (
                deal.title if deal else None
            )

        return None, None

    async def add_delivery_record(
        self,
        *,
        reminder_id: uuid.UUID,
        channel: str,
        outcome: str,
        error_message: str | None,
    ) -> ReminderDeliveryRecordModel:
        record = ReminderDeliveryRecordModel(
            reminder_id=reminder_id,
            channel=channel,
            outcome=outcome,
            error_message=error_message,
        )
        self.db.add(record)
        await self.db.flush()
        return record

    async def _owned(self, model: Any, target_id: uuid.UUID, owner_user_id: uuid.UUID) -> Any:
        return await self.db.scalar(
            select(model).where(model.id == target_id, model.owner_user_id == owner_user_id)
        )

    async def _client(
        self, client_id: uuid.UUID | None, owner_user_id: uuid.UUID
    ) -> ClientModel | None:
        if client_id is None:
            return None
        client: ClientModel | None = await self._owned(ClientModel, client_id, owner_user_id)
        return client

    async def create(self, **values):
        reminder = ReminderModel(**values)
        self.db.add(reminder)
        await self.db.flush()
        await self.db.refresh(reminder)
        return reminder

    async def list_all(
        self,
        owner_user_id: uuid.UUID,
        status: str | None = None,
        target_type: str | None = None,
    ) -> list:
        conditions = [ReminderModel.owner_user_id == owner_user_id]
        if status is not None:
            conditions.append(ReminderModel.status == status)
        if target_type is not None:
            conditions.append(ReminderModel.target_type == target_type)
        result = await self.db.execute(select(ReminderModel).where(*conditions))
        return list(result.scalars().all())

    async def save(self, obj):
        await self.db.flush()
        await self.db.refresh(obj)
        return obj
