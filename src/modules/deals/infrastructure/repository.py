import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import (
    ClientModel,
    ContractModel,
    DealActivityEntryModel,
    DealAttachmentModel,
    DealIntakeModel,
    DealModel,
    InvoiceModel,
    LeadScoreModel,
    ProposalModel,
    ReminderModel,
    UserModel,
)
from src.modules.deals.domain.value_objects.deal_stage import ARCHIVE_AFTER_DAYS, DealStage


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

    async def get_owner_profession(self, owner_user_id: uuid.UUID) -> str | None:
        """Slug nghề của chủ deal — để lead qualifier ước giá + cảnh báo scam theo nghề."""
        return await self.db.scalar(
            select(UserModel.profession).where(UserModel.id == owner_user_id)
        )

    async def get_owner_by_id(self, owner_user_id: uuid.UUID):
        """Chủ deal — cần khi soạn thư gửi cho chính freelancer (tên để chào, email để gửi).

        Đường chạy nền (Celery) không có sẵn object user như đường HTTP, phải tự tra.  #Huynh
        """
        return await self.db.scalar(
            select(UserModel).where(
                UserModel.id == owner_user_id,
                UserModel.deleted_at.is_(None),
            )
        )

    async def get_owner_by_public_link(self, share_token: str):
        """Chủ trang công khai, tra bằng token chia sẻ HOẶC tên đường dẫn riêng.

        Tên hàm cố ý KHÔNG gọi là "by_intake_token": bản cũ tên như vậy nên người đọc
        chỗ gọi không có lý do gì nghi nó nhận thứ khác ngoài token — và đó chính là lý
        do khách vào bằng `/{slug}` xem được trang, điền xong bấm Gửi thì ăn 404.

        Vị từ này TRÙNG với `IntakeFormRepository.get_user_by_token`; hai chỗ phải sửa
        cùng nhau. Không gộp thành một hàm dùng chung vì AGENTS.md cấm module này gọi
        repository của module kia khi chưa có ADR. Test khoá:
        `test_slug_hoat_dong_tren_ca_ba_endpoint_cong_khai`.  #Huynh
        """
        return await self.db.scalar(
            select(UserModel).where(
                or_(
                    UserModel.intake_share_token == share_token,
                    UserModel.profile_slug == share_token,
                ),
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
        archived: bool | None = None,
        sort_by: str = "updated_at",
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
        if archived is not None:
            in_archive = self._archived_predicate()
            conditions.append(in_archive if archived else ~in_archive)
        total = (
            await self.db.scalar(select(func.count()).select_from(DealModel).where(*conditions))
            or 0
        )
        offset = (page - 1) * page_size
        result = await self.db.execute(
            select(DealModel)
            .where(*conditions)
            .order_by(*self._list_order(sort_by))
            .offset(offset)
            .limit(page_size)
        )
        return list(result.scalars().all()), total

    @staticmethod
    def _archived_predicate():  # type: ignore[no-untyped-def]
        """Dự án ĐÃ VÀO KHO: hoàn thành, và đóng cách đây quá `ARCHIVE_AFTER_DAYS`.

        `closed_at IS NOT NULL` là điều kiện bắt buộc chứ không thừa: deal cũ sinh trước khi
        có cột này để trống ngày đóng, mà `NULL < <ngày>` trong SQL cho ra NULL (không phải
        TRUE) — nên nếu viết ẩu thì chúng rơi ra khỏi CẢ hai nhánh: không nằm trên bảng, cũng
        không nằm trong kho. Biến mất hẳn.

        Chỉ tính `completed_and_billed`. `lost` cũng phình y hệt nhưng đợt này cố ý chưa đụng
        tới — mở rộng sau chỉ là thêm giai đoạn vào đây.  #Huynh
        """
        cutoff = datetime.now(UTC) - timedelta(days=ARCHIVE_AFTER_DAYS)
        return and_(
            DealModel.stage == DealStage.COMPLETED_AND_BILLED.value,
            DealModel.closed_at.isnot(None),
            DealModel.closed_at < cutoff,
        )

    @staticmethod
    def _list_order(sort_by: str):  # type: ignore[no-untyped-def]
        """Thứ tự trả về của danh sách deal.

        `updated_at` (mặc định) cho bảng Kanban: deal vừa đổi giai đoạn/sửa thông tin nổi lên
        đầu, tránh cảnh "chuyển giai đoạn xong nhảy xuống giữa danh sách".

        `closed_at` cho ngăn kéo kho: ở đó thứ tự đúng là NGÀY ĐÓNG, không phải lần chạm cuối
        — sửa một chữ trong dự án cũ không được phép đẩy nó lên đầu kho. Kèm `id` làm khoá
        chót để phân trang không bao giờ hoà (bản ghi nhảy giữa hai trang).  #Huynh
        """
        if sort_by == "closed_at":
            return (DealModel.closed_at.desc().nullslast(), DealModel.id)
        return (DealModel.updated_at.desc(), DealModel.id)

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

    async def create_activity_entry(
        self,
        *,
        deal_id: uuid.UUID,
        owner_user_id: uuid.UUID,
        entry_type: str,
        description: str,
    ):
        entry = DealActivityEntryModel(
            deal_id=deal_id,
            owner_user_id=owner_user_id,
            entry_type=entry_type,
            description=description,
        )
        self.db.add(entry)
        await self.db.flush()
        return entry

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
        - ``deleted_at IS NULL``: dự án freelancer đã loại bỏ thì cũng đã loại bỏ khỏi lịch sử
          giá. Thiếu điều kiện này (bản trước thiếu) là neo giá vào những deal mà chính chủ
          coi như không tồn tại.

        Sắp theo ``closed_at`` chứ KHÔNG phải ``updated_at``: "gần nhất" ở đây là gần nhất về
        thời điểm CHỐT DEAL, không phải lần chạm cuối. Bản trước dùng `updated_at`, mà cột đó
        có `onupdate` + trigger PG — nên chỉ cần sửa một chữ trong một dự án cũ là bộ mười mốc
        neo giá xáo lại, và giá gợi ý cho báo giá kế tiếp đổi mà không ai chạm vào giá. Lỗi
        này im lặng tuyệt đối. Cũng nhờ vậy mà việc lưu kho (suy ra từ `closed_at`, không ghi
        gì) không thể ảnh hưởng tới định giá.  #Huynh

        Kho lưu trữ KHÔNG lọc ở đây: freelancer càng lâu năm thì càng nhiều dự án nằm trong
        kho, lọc bỏ là càng làm lâu càng mất mốc giá — đúng ngược ý đồ.
        """

        def _recent_won(extra_filter=None):  # type: ignore[no-untyped-def]
            stmt = select(DealModel.actual_value).where(
                DealModel.owner_user_id == owner_user_id,
                DealModel.deleted_at.is_(None),
                DealModel.stage == DealStage.COMPLETED_AND_BILLED.value,
                DealModel.actual_value.isnot(None),
                DealModel.actual_value > 0,
            )
            if extra_filter is not None:
                stmt = stmt.where(extra_filter)
            return stmt.order_by(DealModel.closed_at.desc().nullslast()).limit(10)

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

    async def get_latest_lead_score(self, deal_id: uuid.UUID, owner_user_id: uuid.UUID):
        """Bản chấm mới nhất của deal, hoặc None nếu chưa chấm lần nào.

        Cùng phép JOIN lọc chủ sở hữu như `list_lead_scores` — `lead_scores` không có cột
        `owner_user_id`, lọc thiếu là ai biết id deal người khác cũng chốt được bản chấm
        của họ.  #Huynh
        """
        return await self.db.scalar(
            select(LeadScoreModel)
            .join(DealModel, DealModel.id == LeadScoreModel.deal_id)
            .where(
                LeadScoreModel.deal_id == deal_id,
                DealModel.owner_user_id == owner_user_id,
            )
            .order_by(LeadScoreModel.generated_at.desc())
            .limit(1)
        )

    async def get_lead_score_by_id(
        self,
        lead_score_id: uuid.UUID,
        deal_id: uuid.UUID,
        owner_user_id: uuid.UUID,
    ):
        """Một bản chấm CỤ THỂ của deal, hoặc None.

        Lọc bằng CẢ ba: id bản chấm, id deal, và chủ sở hữu. Thiếu vế `deal_id` thì biết id
        một bản chấm là chốt được nó sang deal khác của chính mình; thiếu vế chủ sở hữu thì
        chốt được bản chấm của người khác.  #Huynh
        """
        return await self.db.scalar(
            select(LeadScoreModel)
            .join(DealModel, DealModel.id == LeadScoreModel.deal_id)
            .where(
                LeadScoreModel.id == lead_score_id,
                LeadScoreModel.deal_id == deal_id,
                DealModel.owner_user_id == owner_user_id,
            )
        )
