import uuid
from dataclasses import dataclass

from sqlalchemy import Select, func, or_, select
from sqlalchemy.exc import DBAPIError
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

# SQLSTATE 55P03 = `lock_not_available`: câu `SELECT ... FOR ... NOWAIT` không giành được khoá.
_LOCK_NOT_AVAILABLE = "55P03"


class RowLockedError(Exception):
    """Hàng đang bị một giao dịch khác giữ khoá, mà ta xin khoá kiểu NOWAIT nên bị từ chối ngay.

    Repository chỉ DỊCH lỗi của driver sang loại ngoại lệ này; nói gì với người dùng là việc
    của service. Chỉ được ném khi gọi với `nowait=True`.  #Huynh
    """


def _is_lock_not_available(exc: DBAPIError) -> bool:
    """Lỗi driver này có phải "không giành được khoá" (55P03) không.

    SQLAlchemy bọc lỗi của asyncpg hai lớp: `DBAPIError.orig` là bản dịch của adapter (có
    `sqlstate`), và lỗi asyncpg gốc (`LockNotAvailableError`) nằm ở `__cause__`. Lần theo cả chuỗi
    để không phụ thuộc vào việc bản SQLAlchemy nào bọc kiểu nào.  #Huynh
    """
    chain: list[BaseException] = []
    error: BaseException | None = exc.orig
    while error is not None and error not in chain:
        chain.append(error)
        error = error.__cause__
    return any(
        _LOCK_NOT_AVAILABLE in (getattr(item, "sqlstate", None), getattr(item, "pgcode", None))
        for item in chain
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

    async def _scalar_for_update(self, statement: Select, *, nowait: bool):
        """Chạy câu SELECT và KHOÁ hàng tìm được tới hết transaction.

        `key_share=True` = FOR NO KEY UPDATE: vẫn chặn mọi UPDATE khác lên hàng (cái ta cần),
        nhưng KHÔNG chặn INSERT của bảng khác trỏ khoá ngoại vào hàng này (hợp đồng, hoá đơn,
        việc của deal).

        `populate_existing` bắt buộc đọc lại cột từ DB: không có nó thì object đã nằm sẵn trong
        phiên giữ nguyên giá trị cũ dù hàng đã đổi.

        `nowait=True`: hàng đang bị khoá thì KHÔNG đứng chờ mà ném `RowLockedError` ngay. Sau lỗi
        này transaction ở trạng thái hỏng cho tới khi rollback, nên chỗ gọi phải kết thúc request
        chứ không được tiếp tục dùng phiên.  #Huynh
        """
        try:
            return await self.db.scalar(
                statement.with_for_update(key_share=True, nowait=nowait).execution_options(
                    populate_existing=True
                )
            )
        except DBAPIError as exc:
            if nowait and _is_lock_not_available(exc):
                raise RowLockedError from exc
            raise

    async def get_by_id_for_update(
        self, proposal_id: uuid.UUID, owner_user_id: uuid.UUID, *, nowait: bool = False
    ):
        """Như `get_by_id` nhưng KHOÁ HÀNG tới hết transaction (`SELECT ... FOR NO KEY UPDATE`).

        Dùng cho `ProposalsService.send`: email đi TRƯỚC khi transaction commit, nên không có
        khoá thì hai request đồng thời (bấm đúp) cùng đọc thấy `draft`, cùng gửi thư, rồi mới
        tranh nhau UPDATE — khách nhận hai thư. Có khoá, request thứ hai không đọc được trạng thái
        cũ nữa: hoặc đứng chờ tới khi request đầu commit rồi mới đọc lại và thấy `sent`, hoặc
        (`nowait=True`) bị từ chối ngay.  #Huynh
        """
        return await self._scalar_for_update(
            select(ProposalModel).where(
                ProposalModel.id == proposal_id,
                ProposalModel.owner_user_id == owner_user_id,
            ),
            nowait=nowait,
        )

    async def get_deal_for_update(
        self, deal_id: uuid.UUID, owner_user_id: uuid.UUID, *, nowait: bool = False
    ):
        """Khoá hàng DEAL — cổng nối tiếp các lượt gửi báo giá của CÙNG MỘT deal.

        Khoá theo từng hàng báo giá thì chỉ chặn được hai lượt gửi cùng một bản. Hai bản nháp
        KHÁC NHAU của một deal gửi gần như cùng lúc thì khoá hai hàng khác nhau, không vướng nhau;
        `get_sent_by_deal` lại là câu đọc thường nên không thấy bản kia chưa commit, và cả hai
        cùng thành `sent`. Khoá hàng deal bắt chúng xếp hàng: lượt sau chỉ chạy tiếp khi lượt
        trước đã commit, nên câu đọc đó thấy đúng.

        THỨ TỰ KHOÁ LÀ BẮT BUỘC: mọi chỗ khoá cả hai hàng đều phải khoá deal TRƯỚC, báo giá SAU
        (xem `ProposalsService._lock_deal_then_proposal`). Đảo thứ tự ở một chỗ nào đó là có thể
        tạo vòng chờ khoá và Postgres sẽ giết một trong hai giao dịch.  #Huynh
        """
        return await self._scalar_for_update(
            select(DealModel).where(
                DealModel.id == deal_id,
                DealModel.owner_user_id == owner_user_id,
            ),
            nowait=nowait,
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
        # Freelancer CHƯA đặt chuyên môn: trả TẤT CẢ mẫu đang bật, không chỉ mẫu dùng chung.
        #
        # Bản trước lọc `profession IS NULL` nên mọi mẫu gắn nghề biến mất sạch — im lặng, và
        # đúng lúc người dùng mới nhất (chưa kịp điền hồ sơ) cần mẫu nhất. Thà cho họ thấy đủ
        # kèm nhãn nghề để tự chọn, còn hơn đưa ra một danh sách rỗng rồi để họ kết luận là
        # admin chưa soạn mẫu nào.  #Huynh
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
