import uuid
from dataclasses import dataclass

from sqlalchemy import Select, func, or_, select
from sqlalchemy.exc import DBAPIError, IntegrityError
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

# SQLSTATE 55P03 = `lock_not_available`: câu `SELECT ... FOR ... NOWAIT` không giành được khoá.
_LOCK_NOT_AVAILABLE = "55P03"

# Chỉ mục duy nhất từng phần của bảng `contracts`: mỗi deal tối đa MỘT hợp đồng ở trạng thái
# `active` hoặc `pending_signatures`. Xem `ContractModel.__table_args__`.
_ONE_LIVE_PER_DEAL_INDEX = "uq_contracts_one_active_per_deal"


class RowLockedError(Exception):
    """Hàng đang bị một giao dịch khác giữ khoá, mà ta xin khoá kiểu NOWAIT nên bị từ chối ngay.

    Repository chỉ DỊCH lỗi của driver sang loại ngoại lệ này; nói gì với người dùng là việc
    của service. Chỉ được ném khi gọi với `nowait=True`.  #Huynh
    """


class LiveContractExistsError(Exception):
    """Deal đã có một hợp đồng khác đang chờ ký / đang hiệu lực (chỉ mục duy nhất từ chối)."""


def _error_chain(error: BaseException | None) -> list[BaseException]:
    """Lỗi và các lỗi gốc của nó (`__cause__`). SQLAlchemy bọc lỗi asyncpg hai lớp: bản dịch của
    adapter ở `DBAPIError.orig`, lỗi asyncpg gốc ở `__cause__` của bản dịch."""
    chain: list[BaseException] = []
    while error is not None and error not in chain:
        chain.append(error)
        error = error.__cause__
    return chain


def _is_lock_not_available(exc: DBAPIError) -> bool:
    """Lỗi driver này có phải "không giành được khoá" (55P03) không."""
    return any(
        _LOCK_NOT_AVAILABLE in (getattr(error, "sqlstate", None), getattr(error, "pgcode", None))
        for error in _error_chain(exc.orig)
    )


def _violates_one_live_per_deal(exc: IntegrityError) -> bool:
    """Lỗi toàn vẹn này có đúng là chỉ mục "mỗi deal một hợp đồng sống" từ chối không."""
    return any(
        getattr(error, "constraint_name", None) == _ONE_LIVE_PER_DEAL_INDEX
        or _ONE_LIVE_PER_DEAL_INDEX in str(error)
        for error in _error_chain(exc.orig)
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

    async def _scalar_for_update(self, statement: Select, *, nowait: bool):
        """Chạy câu SELECT và KHOÁ hàng tìm được tới hết transaction.

        `key_share=True` = FOR NO KEY UPDATE: vẫn chặn mọi UPDATE khác lên hàng (cái ta cần),
        nhưng KHÔNG chặn INSERT của bảng khác trỏ khoá ngoại vào hàng này (hoá đơn, mốc thanh
        toán của hợp đồng).

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
        self, contract_id: uuid.UUID, owner_user_id: uuid.UUID, *, nowait: bool = False
    ):
        """Như `get_by_id` nhưng KHOÁ HÀNG tới hết transaction (`SELECT ... FOR NO KEY UPDATE`).

        Cùng lý do với `ProposalsRepository.get_by_id_for_update`: email đi TRƯỚC khi commit,
        nên không có khoá thì bấm đúp là khách nhận hai (thậm chí năm) tờ hợp đồng.  #Huynh
        """
        return await self._scalar_for_update(
            select(ContractModel).where(
                ContractModel.id == contract_id,
                ContractModel.owner_user_id == owner_user_id,
            ),
            nowait=nowait,
        )

    async def get_deal_for_update(
        self, deal_id: uuid.UUID, owner_user_id: uuid.UUID, *, nowait: bool = False
    ):
        """Khoá hàng DEAL — cổng nối tiếp các lượt gửi hợp đồng của CÙNG MỘT deal.

        Cùng lý do với `ProposalsRepository.get_deal_for_update`. Ở đây còn một lý do nữa: chỉ mục
        duy nhất `uq_contracts_one_active_per_deal` cho phép tối đa một hợp đồng chờ ký / đang
        hiệu lực mỗi deal, nên hai hợp đồng nháp của một deal gửi cùng lúc sẽ va vào nó — lượt
        sau đứng chờ lượt trước (cả lúc gửi thư) rồi nhận lỗi toàn vẹn. Khoá deal bắt chúng xếp
        hàng, và lượt sau thấy hợp đồng kia đã commit để từ chối gọn.

        THỨ TỰ KHOÁ: deal TRƯỚC, hợp đồng SAU (xem `ContractsService._lock_deal_then_contract`).
        #Huynh
        """
        return await self._scalar_for_update(
            select(DealModel).where(
                DealModel.id == deal_id,
                DealModel.owner_user_id == owner_user_id,
            ),
            nowait=nowait,
        )

    async def get_live_contract_for_deal(self, deal_id: uuid.UUID, exclude_id: uuid.UUID):
        """Hợp đồng KHÁC của deal đang chờ khách ký hoặc đang có hiệu lực, nếu có.

        Đúng điều kiện của chỉ mục `uq_contracts_one_active_per_deal`, hỏi trước để từ chối gọn
        thay vì để chỉ mục ném lỗi.  #Huynh
        """
        return await self.db.scalar(
            select(ContractModel)
            .where(
                ContractModel.deal_id == deal_id,
                ContractModel.id != exclude_id,
                ContractModel.status.in_(("active", "pending_signatures")),
            )
            .limit(1)
        )

    async def get_public_by_token(self, share_token: str):
        return await self.db.scalar(
            select(ContractModel).where(ContractModel.share_token == share_token)
        )

    async def get_proposal(self, proposal_id: uuid.UUID):
        return await self.db.scalar(select(ProposalModel).where(ProposalModel.id == proposal_id))

    async def get_client(self, client_id: uuid.UUID):
        return await self.db.scalar(select(ClientModel).where(ClientModel.id == client_id))

    async def has_accepted_proposal(self, deal_id: uuid.UUID, owner_user_id: uuid.UUID) -> bool:
        """Deal này đã có báo giá được khách chấp nhận chưa.

        Cùng câu hỏi và cùng câu truy vấn với `DealsRepository.has_accepted_proposal` — cố ý
        lặp thay vì gọi chéo sang module deals, giữ ranh giới module như các repo khác đang làm.
        """
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
        # Freelancer CHƯA đặt chuyên môn: trả TẤT CẢ mẫu đang bật, không chỉ mẫu dùng chung.
        #
        # Bản trước lọc `profession IS NULL` nên mọi mẫu gắn nghề biến mất sạch — im lặng, và
        # đúng lúc người dùng mới nhất (chưa kịp điền hồ sơ) cần mẫu nhất. Thà cho họ thấy đủ
        # kèm nhãn nghề để tự chọn, còn hơn đưa ra một danh sách rỗng rồi để họ kết luận là
        # admin chưa soạn mẫu nào.  #Huynh
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

    async def get_milestone(self, milestone_id: uuid.UUID, contract_id: uuid.UUID):
        return await self.db.scalar(
            select(ContractPaymentMilestoneModel).where(
                ContractPaymentMilestoneModel.id == milestone_id,
                ContractPaymentMilestoneModel.contract_id == contract_id,
            )
        )

    async def create_milestone(self, **values) -> ContractPaymentMilestoneModel:
        milestone = ContractPaymentMilestoneModel(**values)
        self.db.add(milestone)
        await self.db.flush()
        await self.db.refresh(milestone)
        return milestone

    async def save_milestone(self, milestone: ContractPaymentMilestoneModel):
        await self.db.flush()
        await self.db.refresh(milestone)
        return milestone

    async def delete_milestone(self, milestone: ContractPaymentMilestoneModel) -> None:
        await self.db.delete(milestone)
        await self.db.flush()

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

    async def save_entering_live_status(self, contract):
        """Như `save`, cho hợp đồng VỪA được chuyển sang `pending_signatures`.

        Đó là bước duy nhất đẩy một hợp đồng vào chỗ mà chỉ mục `uq_contracts_one_active_per_deal`
        canh giữ, nên là nơi chỉ mục có thể từ chối. Dịch lỗi đó thành `LiveContractExistsError`
        để service trả 409 gọn thay vì để `IntegrityError` trần rơi xuống thành 500. Sau lỗi này
        transaction ở trạng thái hỏng, nên chỗ gọi phải kết thúc request.  #Huynh
        """
        try:
            return await self.save(contract)
        except IntegrityError as exc:
            if _violates_one_live_per_deal(exc):
                raise LiveContractExistsError from exc
            raise

    async def delete(self, obj) -> None:
        await self.db.delete(obj)
        await self.db.flush()
