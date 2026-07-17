import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import (
    ClientModel,
    ContractModel,
    DealAttachmentModel,
    DealIntakeModel,
    DealModel,
    InvoiceModel,
    LeadScoreModel,
    ProposalModel,
    ReminderModel,
    UserModel,
)


@dataclass
class DealsRepository:
    db: AsyncSession

    async def get_by_id(self, deal_id: uuid.UUID, owner_user_id: uuid.UUID):
        return await self.db.scalar(
            select(DealModel).where(
                DealModel.id == deal_id,
                DealModel.owner_user_id == owner_user_id,
                DealModel.deleted_at.is_(None),
            )
        )

    async def get_owner_by_intake_token(self, share_token: str):
        return await self.db.scalar(
            select(UserModel).where(
                UserModel.intake_share_token == share_token,
                UserModel.status == "active",
                UserModel.deleted_at.is_(None),
            )
        )

    async def find_client_by_name_and_phone(
        self, owner_user_id: uuid.UUID, name: str, phone: str
    ):
        return await self.db.scalar(
            select(ClientModel).where(
                ClientModel.owner_user_id == owner_user_id,
                ClientModel.name == name,
                ClientModel.phone == phone,
                ClientModel.deleted_at.is_(None),
            )
        )

    async def create_client(self, **values):
        client = ClientModel(**values)
        self.db.add(client)
        await self.db.flush()
        await self.db.refresh(client)
        return client

    async def create_intake(self, **values):
        intake = DealIntakeModel(**values)
        self.db.add(intake)
        await self.db.flush()
        await self.db.refresh(intake)
        return intake

    async def get_intake_by_id(self, intake_id: uuid.UUID, owner_user_id: uuid.UUID):
        return await self.db.scalar(
            select(DealIntakeModel).where(
                DealIntakeModel.id == intake_id,
                DealIntakeModel.owner_user_id == owner_user_id,
                DealIntakeModel.deleted_at.is_(None),
            )
        )

    async def get_intake_for_deal(
        self, deal_id: uuid.UUID, client_id: uuid.UUID, owner_user_id: uuid.UUID
    ):
        """Phiếu tiếp nhận của ĐÚNG deal này.

        Tra theo `deal_id` trước. Chỉ khi không có (phiếu cũ tạo trước khi có cột đó) mới
        rơi về tra theo client — chấp nhận rủi ro lấy nhầm phiếu, nhưng chỉ với dữ liệu cũ.

        Trước đây LUÔN tra theo client: một khách gửi form hai lần cho hai dự án → deal cũ
        bị chấm điểm (và báo giá!) bằng brief của dự án mới.  #Huynh
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
        return await self.db.scalar(
            select(DealIntakeModel)
            .where(
                DealIntakeModel.client_id == client_id,
                DealIntakeModel.owner_user_id == owner_user_id,
                DealIntakeModel.deleted_at.is_(None),
            )
            .order_by(DealIntakeModel.created_at.desc())
        )

    async def list_intakes(
        self, owner_user_id: uuid.UUID, page: int = 1, page_size: int = 20
    ) -> tuple[list, int]:
        conditions = [
            DealIntakeModel.owner_user_id == owner_user_id,
            DealIntakeModel.deleted_at.is_(None),
        ]
        total = (
            await self.db.scalar(
                select(func.count()).select_from(DealIntakeModel).where(*conditions)
            )
            or 0
        )
        offset = (page - 1) * page_size
        result = await self.db.execute(
            select(DealIntakeModel)
            .where(*conditions)
            .order_by(DealIntakeModel.submitted_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        return list(result.scalars().all()), total

    async def get_client_by_id(self, client_id: uuid.UUID, owner_user_id: uuid.UUID):
        return await self.db.scalar(
            select(ClientModel).where(
                ClientModel.id == client_id,
                ClientModel.owner_user_id == owner_user_id,
                ClientModel.deleted_at.is_(None),
            )
        )

    async def has_accepted_proposal(self, deal_id: uuid.UUID, owner_user_id: uuid.UUID) -> bool:
        count = await self.db.scalar(
            select(func.count())
            .select_from(ProposalModel)
            .where(
                ProposalModel.deal_id == deal_id,
                ProposalModel.owner_user_id == owner_user_id,
                ProposalModel.status == "accepted",
            )
        )
        return bool(count)

    async def list_attachments_with_text(self, deal_id: uuid.UUID, owner_user_id: uuid.UUID):
        """File đính kèm ĐÃ BÓC ĐƯỢC CHỮ — chỉ những file này mới đưa cho AI đọc.

        Bỏ qua file không bóc được (PDF scan là ảnh, ảnh chụp, .docx...): đưa vào prompt
        cũng chỉ là một cái tên file, không giúp AI chấm chuẩn hơn.  #Huynh
        """
        rows = await self.db.scalars(
            select(DealAttachmentModel)
            .where(
                DealAttachmentModel.deal_id == deal_id,
                DealAttachmentModel.owner_user_id == owner_user_id,
                DealAttachmentModel.extracted_text.isnot(None),
            )
            .order_by(DealAttachmentModel.created_at)
        )
        return list(rows)

    async def has_signed_contract(self, deal_id: uuid.UUID, owner_user_id: uuid.UUID) -> bool:
        """Deal này đã có hợp đồng ở trạng thái `active` chưa.

        `active` = freelancer đã GHI NHẬN rằng hai bên ký xong (ký ngoài hệ thống — khách
        của freelancer không có tài khoản SoloDesk). SoloDesk là SỔ THEO DÕI, không phải
        nền tảng chữ ký số.

        Cần hàm này vì trước đây chuyển deal sang "Đang triển khai" CHỈ đòi có báo giá
        được chấp nhận — không đòi hợp đồng nào cả. Freelancer bắt tay làm việc mà không
        có hợp đồng, đúng thứ SoloDesk sinh ra để ngăn.  #Huynh
        """
        count = await self.db.scalar(
            select(func.count())
            .select_from(ContractModel)
            .where(
                ContractModel.deal_id == deal_id,
                ContractModel.owner_user_id == owner_user_id,
                ContractModel.status == "active",
            )
        )
        return bool(count)

    async def has_invoice(self, deal_id: uuid.UUID, owner_user_id: uuid.UUID) -> bool:
        count = await self.db.scalar(
            select(func.count())
            .select_from(InvoiceModel)
            .where(InvoiceModel.deal_id == deal_id, InvoiceModel.owner_user_id == owner_user_id)
        )
        return bool(count)

    async def invoiced_total(self, deal_id: uuid.UUID, owner_user_id: uuid.UUID) -> Decimal | None:
        """Tổng tiền ĐÃ XUẤT HOÁ ĐƠN cho deal này. Bỏ hoá đơn đã huỷ (`void`).

        Đây là con số dùng để điền `actual_value` khi deal hoàn thành — và chính nó là mốc
        neo giá cho các deal sau. Xem `comparable_deal_values()`.  #Huynh
        """
        total = await self.db.scalar(
            select(func.sum(InvoiceModel.total)).where(
                InvoiceModel.deal_id == deal_id,
                InvoiceModel.owner_user_id == owner_user_id,
                InvoiceModel.status != "void",
            )
        )
        return Decimal(total) if total else None

    async def cancel_pending_reminders(self, deal_id: uuid.UUID, owner_user_id: uuid.UUID) -> None:
        await self.db.execute(
            update(ReminderModel)
            .where(
                ReminderModel.owner_user_id == owner_user_id,
                ReminderModel.target_type == "deal",
                ReminderModel.target_id == deal_id,
                ReminderModel.status == "pending",
            )
            .values(status="cancelled")
        )

    async def create(self, **values):
        deal = DealModel(**values)
        self.db.add(deal)
        await self.db.flush()
        await self.db.refresh(deal)
        return deal

    async def get_deal_by_client_id(self, client_id: uuid.UUID, owner_user_id: uuid.UUID):
        return await self.db.scalar(
            select(DealModel)
            .where(
                DealModel.client_id == client_id,
                DealModel.owner_user_id == owner_user_id,
                DealModel.deleted_at.is_(None),
            )
            .order_by(DealModel.created_at.desc())
        )

    async def list_all(
        self,
        owner_user_id: uuid.UUID,
        title: str | None = None,
        stage: str | None = None,
        client_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list, int]:
        conditions = [DealModel.owner_user_id == owner_user_id, DealModel.deleted_at.is_(None)]
        if title is not None:
            conditions.append(DealModel.title.ilike(f"%{title}%"))
        if stage is not None:
            conditions.append(DealModel.stage == stage)
        if client_id is not None:
            conditions.append(DealModel.client_id == client_id)
        total = (
            await self.db.scalar(select(func.count()).select_from(DealModel).where(*conditions))
            or 0
        )
        offset = (page - 1) * page_size
        result = await self.db.execute(
            select(DealModel)
            .where(*conditions)
            .order_by(DealModel.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        return list(result.scalars().all()), total

    async def create_lead_score(
        self,
        *,
        id: uuid.UUID,
        deal_id: uuid.UUID,
        score: int,
        confidence: float,
        reasoning: str,
        model_version: str,
        generated_at,
        project_type: str | None = None,
        budget_signal: str | None = None,
        timeline_signal: str | None = None,
        urgency_signal: str | None = None,
        red_flags: list | None = None,
        breakdown: list | None = None,
        next_step: str | None = None,
        detected_signals: list | None = None,
        prompt_version: str | None = None,
    ):
        model = LeadScoreModel(
            id=id,
            deal_id=deal_id,
            score=score,
            confidence=confidence,
            reasoning=reasoning,
            model_version=model_version,
            generated_at=generated_at,
            project_type=project_type,
            budget_signal=budget_signal,
            timeline_signal=timeline_signal,
            urgency_signal=urgency_signal,
            red_flags=red_flags,
            breakdown=breakdown,
            next_step=next_step,
            detected_signals=detected_signals,
            prompt_version=prompt_version,
        )
        self.db.add(model)
        await self.db.flush()
        return model

    async def save(self, obj):
        await self.db.flush()
        await self.db.refresh(obj)
        return obj

    async def comparable_deal_values(
        self, owner_user_id: uuid.UUID, service_category: str | None
    ) -> tuple[list[Decimal], list[Decimal]]:
        """Giá THẬT của các deal đã chốt xong — dùng làm mốc neo khi báo giá.

        Trả về ``(cùng_nhóm_dịch_vụ, mọi_nhóm)``.

        Điều kiện lọc, và vì sao từng cái:

        - ``stage = completed_and_billed``: chỉ deal ĐÃ XONG và ĐÃ XUẤT HOÁ ĐƠN. Deal đang
          chào giá thì chưa biết khách có gật không — lấy nó làm mốc là neo vào một con số
          chưa ai đồng ý.
        - ``actual_value IS NOT NULL``: TIỀN THẬT THU ĐƯỢC, không phải `estimated_value`
          (con số freelancer tự ước lúc mới tạo deal, thường sai).
        - ``LIMIT 10`` gần nhất: giá năm 2023 không còn đúng cho năm 2026.

        Lọc theo ``service_category`` chính là lời giải cho chuyện "một freelancer làm nhiều
        nghề": lịch sử báo giá thiết kế không được dùng để định giá dự án lập trình.  #Huynh
        """

        def _recent_won(extra_filter=None):  # type: ignore[no-untyped-def]
            stmt = select(DealModel.actual_value).where(
                DealModel.owner_user_id == owner_user_id,
                DealModel.stage == "completed_and_billed",
                DealModel.actual_value.isnot(None),
                DealModel.actual_value > 0,
            )
            if extra_filter is not None:
                stmt = stmt.where(extra_filter)
            return stmt.order_by(DealModel.updated_at.desc()).limit(10)

        any_category = list(await self.db.scalars(_recent_won()))

        same_category: list[Decimal] = []
        if service_category:
            same_category = list(
                await self.db.scalars(
                    _recent_won(DealModel.service_category == service_category)
                )
            )

        return same_category, any_category

    async def list_lead_scores(self, deal_id: uuid.UUID, owner_user_id: uuid.UUID) -> list:
        """Lịch sử chấm điểm của một deal — mới nhất trước.

        JOIN sang `deals` để lọc theo chủ sở hữu ngay trong WHERE. `lead_scores` không có
        cột `owner_user_id`, nên nếu chỉ lọc theo `deal_id` thì ai biết id deal của người
        khác là đọc được kết quả chấm điểm của họ.  #Huynh
        """
        rows = await self.db.scalars(
            select(LeadScoreModel)
            .join(DealModel, DealModel.id == LeadScoreModel.deal_id)
            .where(
                LeadScoreModel.deal_id == deal_id,
                DealModel.owner_user_id == owner_user_id,
            )
            .order_by(LeadScoreModel.generated_at.desc())
        )
        return list(rows)
