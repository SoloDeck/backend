import uuid
from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import (
    ClientModel,
    ContractModel,
    ContractPaymentMilestoneModel,
    DealModel,
    PlanModel,
    ProposalModel,
    SubscriptionModel,
    SystemTemplateModel,
    UserModel,
)


@dataclass
class ContractsRepository:
    db: AsyncSession

    async def get_by_id(self, contract_id: uuid.UUID, owner_user_id: uuid.UUID):
        return await self.db.scalar(
            select(ContractModel).where(
                ContractModel.id == contract_id,
                ContractModel.owner_user_id == owner_user_id,
            )
        )

    async def get_public_by_token(self, share_token: str):
        return await self.db.scalar(
            select(ContractModel).where(ContractModel.share_token == share_token)
        )

    async def get_proposal(self, proposal_id: uuid.UUID):
        return await self.db.scalar(select(ProposalModel).where(ProposalModel.id == proposal_id))

    async def get_client(self, client_id: uuid.UUID):
        return await self.db.scalar(select(ClientModel).where(ClientModel.id == client_id))

    async def count_by_deal(self, deal_id: uuid.UUID) -> int:
        return (
            await self.db.scalar(
                select(func.count())
                .select_from(ContractModel)
                .where(ContractModel.deal_id == deal_id)
            )
            or 0
        )

    async def create(self, **values):
        contract = ContractModel(**values)
        self.db.add(contract)
        await self.db.flush()
        await self.db.refresh(contract)
        return contract

    async def list_all(
        self,
        owner_user_id: uuid.UUID,
        status: str | None = None,
        deal_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list, int]:
        conditions = [ContractModel.owner_user_id == owner_user_id]
        if status is not None:
            conditions.append(ContractModel.status == status)
        if deal_id is not None:
            conditions.append(ContractModel.deal_id == deal_id)
        total = (
            await self.db.scalar(select(func.count()).select_from(ContractModel).where(*conditions))
            or 0
        )
        offset = (page - 1) * page_size
        result = await self.db.execute(
            select(ContractModel)
            .where(*conditions)
            .order_by(ContractModel.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        return list(result.scalars().all()), total

    async def get_deal(self, deal_id: uuid.UUID):
        return await self.db.scalar(select(DealModel).where(DealModel.id == deal_id))

    async def get_user(self, user_id: uuid.UUID):
        return await self.db.scalar(select(UserModel).where(UserModel.id == user_id))

    def _usable_template_conditions(self, template_type: str, profession: str | None) -> list:
        """Điều kiện "mẫu freelancer được phép dùng": active + đúng loại + (đúng nghề HOẶC
        dùng chung). Freelancer chưa chọn nghề thì chỉ mẫu dùng chung.  #Huynh"""
        conditions = [
            SystemTemplateModel.template_type == template_type,
            SystemTemplateModel.is_active.is_(True),
        ]
        if profession:
            conditions.append(
                or_(
                    SystemTemplateModel.profession == profession,
                    SystemTemplateModel.profession.is_(None),
                )
            )
        else:
            conditions.append(SystemTemplateModel.profession.is_(None))
        return conditions

    async def list_active_templates(self, *, template_type: str, profession: str | None) -> list:
        """Các mẫu freelancer được chọn khi sinh — để FE hiện danh sách. Mẫu đúng nghề
        đứng trước mẫu dùng chung."""
        result = await self.db.execute(
            select(SystemTemplateModel)
            .where(*self._usable_template_conditions(template_type, profession))
            .order_by(
                SystemTemplateModel.profession.is_(None),
                SystemTemplateModel.name,
            )
        )
        return list(result.scalars().all())

    async def get_template_for_use(
        self, template_id: uuid.UUID, *, template_type: str, profession: str | None
    ):
        """Mẫu theo id — CHỈ trả nếu freelancer được phép dùng (active + đúng loại + đúng
        nghề/dùng chung). Chặn truyền id mẫu của nghề khác hay mẫu đã tắt.  #Huynh"""
        return await self.db.scalar(
            select(SystemTemplateModel).where(
                SystemTemplateModel.id == template_id,
                *self._usable_template_conditions(template_type, profession),
            )
        )

    async def get_milestones(self, contract_id: uuid.UUID) -> list:
        """Lịch thanh toán của hợp đồng, theo đúng thứ tự sort_order — để in vào bản
        render. Cùng nguồn với danh sách 'Mốc thanh toán' trên màn hình.  #Huynh"""
        result = await self.db.execute(
            select(ContractPaymentMilestoneModel)
            .where(ContractPaymentMilestoneModel.contract_id == contract_id)
            .order_by(ContractPaymentMilestoneModel.sort_order)
        )
        return list(result.scalars().all())

    async def get_subscription(self, user_id: uuid.UUID):
        return await self.db.scalar(
            select(SubscriptionModel).where(SubscriptionModel.user_id == user_id)
        )

    async def get_plan(self, plan_id: uuid.UUID):
        return await self.db.scalar(select(PlanModel).where(PlanModel.id == plan_id))

    async def save(self, obj):
        await self.db.flush()
        await self.db.refresh(obj)
        return obj

    async def delete(self, obj) -> None:
        await self.db.delete(obj)
        await self.db.flush()
