import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import (
    ClientCommunicationLogModel,
    ClientModel,
    ContractModel,
    DealModel,
    InvoiceModel,
)


@dataclass
class ClientsRepository:
    db: AsyncSession

    async def get_by_id(self, client_id: uuid.UUID, owner_user_id: uuid.UUID):
        return await self.db.scalar(
            select(ClientModel).where(
                ClientModel.id == client_id,
                ClientModel.owner_user_id == owner_user_id,
                ClientModel.deleted_at.is_(None),
            )
        )

    async def create(self, **values):
        client = ClientModel(**values)
        self.db.add(client)
        await self.db.flush()
        await self.db.refresh(client)
        return client

    async def list_all(
        self,
        owner_user_id: uuid.UUID,
        status: str | None = None,
        name: str | None = None,
        email: str | None = None,
    ) -> list:
        conditions = [ClientModel.owner_user_id == owner_user_id, ClientModel.deleted_at.is_(None)]
        if status is not None:
            conditions.append(ClientModel.status == status)
        if name is not None:
            conditions.append(ClientModel.name.ilike(f"%{name}%"))
        if email is not None:
            conditions.append(ClientModel.email.ilike(f"%{email}%"))
        result = await self.db.execute(
            # Trước đây không có order_by -> thứ tự trả về tùy DB. Sắp theo ngày cập nhật
            # mới nhất để client vừa thêm/sửa luôn ở đầu danh sách.
            select(ClientModel).where(*conditions).order_by(ClientModel.updated_at.desc())
        )
        return list(result.scalars().all())

    async def add_comm_log(self, **values):
        log = ClientCommunicationLogModel(**values)
        self.db.add(log)
        await self.db.flush()
        await self.db.refresh(log)
        return log

    async def list_comm_logs(self, owner_user_id: uuid.UUID, client_id: uuid.UUID) -> list:
        result = await self.db.execute(
            select(ClientCommunicationLogModel).where(
                ClientCommunicationLogModel.client_id == client_id,
                ClientCommunicationLogModel.owner_user_id == owner_user_id,
            )
        )
        return list(result.scalars().all())

    # Khoá của dict trả về ở count_transactions. Thứ tự này cũng là thứ tự đọc lên
    # trong câu báo lỗi: dự án -> hoá đơn -> hợp đồng, theo đúng luồng nghiệp vụ.
    TRANSACTION_MODELS = (
        ("deals", DealModel),
        ("invoices", InvoiceModel),
        ("contracts", ContractModel),
    )

    async def count_transactions(self, client_id: uuid.UUID) -> dict[str, int]:
        """Đếm deal/invoice/contract đang trỏ tới khách, KỂ CẢ bản đã xoá mềm.

        Không lọc `deleted_at` là CỐ Ý (xem 163fb7f): hoá đơn và hợp đồng là chứng từ,
        xoá khách đi thì chúng mất chỗ bám. Đổi lại, service phải nói cho người dùng biết
        điều đó — xem `_deletion_blocked_message`, vì họ vừa xoá dự án xong nên nhìn màn
        hình sẽ tưởng chẳng còn gì.

        Trả về SỐ LƯỢNG chứ không phải true/false, để câu báo lỗi gọi được tên cái đang vướng.
        """
        return {
            key: (
                await self.db.scalar(
                    select(func.count()).select_from(Model).where(Model.client_id == client_id)
                )
                or 0
            )
            for key, Model in self.TRANSACTION_MODELS
        }

    async def save(self, obj):
        await self.db.flush()
        await self.db.refresh(obj)
        return obj
