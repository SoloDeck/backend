import uuid
from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import (
    ClientModel,
    DealIntakeModel,
    DealModel,
    PlanModel,
    ProposalModel,
    SubscriptionModel,
    SystemTemplateModel,
    UserModel,
)


@dataclass
class ProposalsRepository:
    db: AsyncSession

    async def get_by_id(self, proposal_id: uuid.UUID, owner_user_id: uuid.UUID):
        return await self.db.scalar(
            select(ProposalModel).where(
                ProposalModel.id == proposal_id,
                ProposalModel.owner_user_id == owner_user_id,
            )
        )

    async def get_public_by_token(self, share_token: str):
        return await self.db.scalar(
            select(ProposalModel).where(ProposalModel.share_token == share_token)
        )

    async def count_by_deal(self, deal_id: uuid.UUID) -> int:
        return (
            await self.db.scalar(
                select(func.count())
                .select_from(ProposalModel)
                .where(ProposalModel.deal_id == deal_id)
            )
            or 0
        )

    async def create(self, **values):
        proposal = ProposalModel(**values)
        self.db.add(proposal)
        await self.db.flush()
        await self.db.refresh(proposal)
        return proposal

    async def list_all(
        self,
        owner_user_id: uuid.UUID,
        status: str | None = None,
        deal_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list, int]:
        conditions = [ProposalModel.owner_user_id == owner_user_id]
        if status is not None:
            conditions.append(ProposalModel.status == status)
        if deal_id is not None:
            conditions.append(ProposalModel.deal_id == deal_id)
        total = (
            await self.db.scalar(select(func.count()).select_from(ProposalModel).where(*conditions))
            or 0
        )
        offset = (page - 1) * page_size
        result = await self.db.execute(
            select(ProposalModel)
            .where(*conditions)
            .order_by(ProposalModel.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        return list(result.scalars().all()), total

    async def get_sent_by_deal(self, deal_id: uuid.UUID, exclude_id: uuid.UUID):
        return await self.db.scalar(
            select(ProposalModel).where(
                ProposalModel.deal_id == deal_id,
                ProposalModel.status == "sent",
                ProposalModel.id != exclude_id,
            )
        )

    async def get_accepted_by_deal(self, deal_id: uuid.UUID, owner_user_id: uuid.UUID):
        """Báo giá ĐÃ CHỐT (mới nhất) của deal — nguồn mốc thanh toán để sinh task khi vào
        giai đoạn triển khai. Nhiều bản chốt thì lấy version cao nhất.  #Huynh"""
        return await self.db.scalar(
            select(ProposalModel)
            .where(
                ProposalModel.deal_id == deal_id,
                ProposalModel.owner_user_id == owner_user_id,
                ProposalModel.status == "accepted",
            )
            .order_by(ProposalModel.version_number.desc())
        )

    async def get_deal(self, deal_id: uuid.UUID):
        return await self.db.scalar(select(DealModel).where(DealModel.id == deal_id))

    async def get_client(self, client_id: uuid.UUID):
        return await self.db.scalar(select(ClientModel).where(ClientModel.id == client_id))

    async def get_user(self, user_id: uuid.UUID):
        return await self.db.scalar(select(UserModel).where(UserModel.id == user_id))

    def _usable_template_conditions(self, template_type: str, profession: str | None) -> list:
        """Mẫu freelancer được phép dùng: active + đúng loại + (đúng nghề HOẶC dùng chung).

        Giống hệt bản ở ContractsRepository — cố ý lặp thay vì chia sẻ, để mỗi module giữ
        đường DB riêng theo AGENTS.md.  #Huynh
        """
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
        return await self.db.scalar(
            select(SystemTemplateModel).where(
                SystemTemplateModel.id == template_id,
                *self._usable_template_conditions(template_type, profession),
            )
        )

    async def get_intake_for_deal(
        self, deal_id: uuid.UUID, client_id: uuid.UUID, owner_user_id: uuid.UUID
    ):
        """Phiếu tiếp nhận của ĐÚNG deal này.

        Trước đây tra theo client: một khách gửi Biểu mẫu tiếp nhận hai lần cho hai dự án
        → báo giá của deal cũ được soạn bằng brief của dự án MỚI. Freelancer gửi cho khách
        một bản báo giá cho DỰ ÁN SAI.  #Huynh
        """
        intake = await self.db.scalar(
            select(DealIntakeModel).where(
                DealIntakeModel.deal_id == deal_id,
                DealIntakeModel.owner_user_id == owner_user_id,
                DealIntakeModel.deleted_at.is_(None),
            )
        )
        if intake is not None:
            return intake

        return await self.get_intake_by_client_id(client_id, owner_user_id)

    async def get_intake_by_client_id(self, client_id: uuid.UUID, owner_user_id: uuid.UUID):
        """Phiếu tiếp nhận mới nhất của khách — chứa NGUYÊN VĂN yêu cầu họ viết.

        AI soạn báo giá trước đây không đọc bảng này (chỉ lead_qualifier đọc), nên nguồn
        tin giàu nhất bị bỏ phí và báo giá viết ra rất mỏng.  #Huynh
        """
        return await self.db.scalar(
            select(DealIntakeModel)
            .where(
                DealIntakeModel.client_id == client_id,
                DealIntakeModel.owner_user_id == owner_user_id,
                DealIntakeModel.deleted_at.is_(None),
            )
            .order_by(DealIntakeModel.created_at.desc())
        )

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
