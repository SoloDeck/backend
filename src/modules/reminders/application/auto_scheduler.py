"""Tự phát hiện việc cần nhắc rồi soạn sẵn lời nhắc.

Trước file này, hệ thống chỉ gửi được lời nhắc do người dùng TỰ TẠO TAY — tức freelancer
vẫn phải tự nhớ hoá đơn nào sắp tới hạn, khách nào chưa phản hồi báo giá. Phiếu đòi "nhắc
nhở TỰ ĐỘNG", và đây là phần đó.

**Bộ máy này CHỈ TẠO, KHÔNG GỬI.** Nó sinh ra `ReminderModel` ở trạng thái `pending`; việc
gửi vẫn do `send_pending_reminders` + `ReminderDeliveryService` đã có lo. Nhờ vậy không có
đường gửi thứ hai để lệch khỏi đường thứ nhất.  #Huynh
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import structlog
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import (
    ClientCommunicationLogModel,
    ClientModel,
    ContractModel,
    DealModel,
    InvoiceModel,
    ProposalModel,
    ReminderModel,
    ReminderRuleModel,
    UserModel,
)
from src.modules.notifications.application.service import (
    TYPE_REMINDER_DRAFTED,
    NotificationService,
)
from src.modules.reminders.domain.value_objects.reminder_rules import (
    RuleType,
    effective_template,
    render_reminder_template,
)

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class Candidate:
    """Một việc đáng nhắc mà bộ máy tìm ra."""

    owner_user_id: uuid.UUID
    target_type: str
    target_id: uuid.UUID
    rule: ReminderRuleModel
    message: str
    client_name: str


@dataclass
class AutoReminderScheduler:
    """Quét toàn hệ thống mỗi ngày một lần.

    Thuần async, không biết Celery là gì — cùng lối `ReminderDeliveryService`, để test
    được bằng AsyncMock và để chạy tay lúc kiểm chứng.
    """

    db: AsyncSession
    # Để trống thì "hôm nay" tính theo MÚI GIỜ CỦA TỪNG NGƯỜI (xem `_today_for`). Trước
    # đây field này mặc định `datetime.now(UTC).date()`, và đó là một lỗi thật: người dùng
    # ở UTC+7 thì từ 17h UTC trở đi đã sang ngày mới, trong khi scheduler vẫn nghĩ là hôm
    # qua — quy tắc "nhắc trước hạn 3 ngày" bắn lệch mất một ngày. Chỉ test mới truyền
    # giá trị vào đây để cố định mốc thời gian.  #Huynh
    today: date | None = None
    # Múi giờ của từng chủ sở hữu, nạp MỘT lần đầu lượt quét. Hỏi lẻ từng lời nhắc là N+1
    # trên một tác vụ vốn đã chạy khắp hệ thống.
    _timezones: dict[uuid.UUID, str] = field(default_factory=dict)

    async def run(self) -> dict[str, int]:
        await self._load_timezones()
        candidates: list[Candidate] = []
        for finder in (
            self._proposals_awaiting_reply,
            self._contracts_awaiting_signature,
            self._invoices_due_soon,
            self._invoices_overdue,
            self._clients_gone_quiet,
        ):
            candidates.extend(await finder())

        fresh = await self._drop_duplicates(candidates)
        for candidate in fresh:
            self.db.add(self._build_reminder(candidate))
        await self.db.flush()

        await self._notify_owners(fresh)
        counts = {"found": len(candidates), "created": len(fresh)}
        if fresh:
            log.info("auto_reminders.created", **counts)
        return counts

    # ------------------------------------------------------------------------------
    # Năm quy tắc
    # ------------------------------------------------------------------------------

    async def _proposals_awaiting_reply(self) -> list[Candidate]:
        """Đã gửi báo giá N ngày mà khách chưa trả lời.

        `responded_at IS NULL` là điều kiện then chốt: khách đã phản hồi rồi mà còn nhắc
        "anh xem giúp em nhé" thì lộ ra ngay là máy gửi.
        """
        rows = await self._join_rule(
            RuleType.PROPOSAL_FOLLOW_UP,
            select(ProposalModel, ClientModel.name, DealModel.title, ReminderRuleModel)
            .join(DealModel, DealModel.id == ProposalModel.deal_id)
            .join(ClientModel, ClientModel.id == DealModel.client_id)
            .where(
                ProposalModel.status == "sent",
                ProposalModel.responded_at.is_(None),
                ProposalModel.sent_at.is_not(None),
            ),
            ProposalModel.owner_user_id,
        )
        out = []
        for proposal, client_name, deal_title, rule in rows:
            if not self._is_older_than(proposal.sent_at, rule.offset_days):
                continue
            out.append(
                Candidate(
                    owner_user_id=proposal.owner_user_id,
                    target_type="deal",
                    target_id=proposal.deal_id,
                    rule=rule,
                    client_name=client_name,
                    message=self._render(
                        RuleType.PROPOSAL_FOLLOW_UP,
                        rule,
                        {"client_name": client_name, "deal_title": deal_title},
                    ),
                )
            )
        return out

    async def _contracts_awaiting_signature(self) -> list[Candidate]:
        """Hợp đồng đã gửi N ngày mà khách chưa ký."""
        rows = await self._join_rule(
            RuleType.CONTRACT_SIGNING_NUDGE,
            select(ContractModel, ClientModel.name, DealModel.title, ReminderRuleModel)
            .join(DealModel, DealModel.id == ContractModel.deal_id)
            .join(ClientModel, ClientModel.id == ContractModel.client_id)
            .where(
                ContractModel.status == "pending_signatures",
                ContractModel.signed_by_client_at.is_(None),
            ),
            ContractModel.owner_user_id,
        )
        out = []
        for contract, client_name, deal_title, rule in rows:
            if not self._is_older_than(contract.updated_at, rule.offset_days):
                continue
            out.append(
                Candidate(
                    owner_user_id=contract.owner_user_id,
                    target_type="contract",
                    target_id=contract.id,
                    rule=rule,
                    client_name=client_name,
                    message=self._render(
                        RuleType.CONTRACT_SIGNING_NUDGE,
                        rule,
                        {"client_name": client_name, "deal_title": deal_title},
                    ),
                )
            )
        return out

    async def _invoices_due_soon(self) -> list[Candidate]:
        """Hoá đơn còn N ngày nữa tới hạn.

        Chỉ lấy `sent` và `partially_paid`. `draft` là hoá đơn chưa gửi cho khách — nhắc
        khách trả một hoá đơn họ chưa từng nhận thì vô nghĩa. Cùng lý lẽ với
        `mark_overdue_invoices`.
        """
        rows = await self._join_rule(
            RuleType.PAYMENT_DUE,
            select(InvoiceModel, ClientModel.name, ReminderRuleModel).join(
                ClientModel, ClientModel.id == InvoiceModel.client_id
            ),
            InvoiceModel.owner_user_id,
            extra=InvoiceModel.status.in_(("sent", "partially_paid")),
        )
        out = []
        for invoice, client_name, rule in rows:
            today = self._today_for(invoice.owner_user_id)
            if invoice.due_date != today + timedelta(days=rule.offset_days):
                continue
            out.append(
                self._invoice_candidate(
                    invoice,
                    client_name,
                    rule,
                    message=self._render(
                        RuleType.PAYMENT_DUE,
                        rule,
                        {
                            "client_name": client_name,
                            "invoice_number": invoice.invoice_number,
                            "due_date": self._vn_date(invoice.due_date),
                            "amount": self._money(invoice),
                        },
                    ),
                )
            )
        return out

    async def _invoices_overdue(self) -> list[Candidate]:
        """Hoá đơn đã quá hạn N ngày. `mark_overdue_invoices` lo phần chuyển trạng thái."""
        rows = await self._join_rule(
            RuleType.PAYMENT_OVERDUE,
            select(InvoiceModel, ClientModel.name, ReminderRuleModel).join(
                ClientModel, ClientModel.id == InvoiceModel.client_id
            ),
            InvoiceModel.owner_user_id,
            extra=InvoiceModel.status == "overdue",
        )
        out = []
        for invoice, client_name, rule in rows:
            days_late = (self._today_for(invoice.owner_user_id) - invoice.due_date).days
            if days_late < rule.offset_days:
                continue
            out.append(
                self._invoice_candidate(
                    invoice,
                    client_name,
                    rule,
                    message=self._render(
                        RuleType.PAYMENT_OVERDUE,
                        rule,
                        {
                            "client_name": client_name,
                            "invoice_number": invoice.invoice_number,
                            "days_late": str(days_late),
                            "due_date": self._vn_date(invoice.due_date),
                            "amount": self._money(invoice),
                        },
                    ),
                )
            )
        return out

    async def _clients_gone_quiet(self) -> list[Candidate]:
        """Khách đã lâu không liên lạc.

        Quy tắc duy nhất chạm tới khách KHÔNG có việc gì đang làm dở, nên mặc định tắt.
        Chỉ xét khách còn `active`/`prospect` — khách đã `archived` là chủ động cắt liên
        lạc, nhắc lại là phiền.
        """
        rows = await self._join_rule(
            RuleType.RE_ENGAGEMENT,
            select(ClientModel, ClientModel.name, ReminderRuleModel),
            ClientModel.owner_user_id,
            extra=ClientModel.status.in_(("active", "prospect")),
        )
        out = []
        for client, client_name, rule in rows:
            last = await self.db.scalar(
                select(ClientCommunicationLogModel.communicated_at)
                .where(ClientCommunicationLogModel.client_id == client.id)
                .order_by(ClientCommunicationLogModel.communicated_at.desc())
                .limit(1)
            )
            # Chưa từng liên lạc thì lấy ngày tạo khách làm mốc — khách nhập vào rồi bỏ
            # quên nửa năm cũng đáng nhắc y như khách từng nói chuyện rồi im.
            since = last or client.created_at
            if not self._is_older_than(since, rule.offset_days):
                continue
            out.append(
                Candidate(
                    owner_user_id=client.owner_user_id,
                    target_type="client",
                    target_id=client.id,
                    rule=rule,
                    client_name=client_name,
                    message=self._render(
                        RuleType.RE_ENGAGEMENT,
                        rule,
                        {"client_name": client_name},
                    ),
                )
            )
        return out

    # ------------------------------------------------------------------------------
    # Chống trùng — chỗ dễ sai nhất cả file
    # ------------------------------------------------------------------------------

    async def _drop_duplicates(self, candidates: list[Candidate]) -> list[Candidate]:
        """Bỏ ứng viên đã có lời nhắc rồi.

        Không có bước này thì một hoá đơn quá hạn sinh ra một lời nhắc MỖI NGÀY — tháng
        sau khách nhận ba mươi cái email giống hệt nhau và freelancer mất khách.

        Bỏ qua nếu đã tồn tại lời nhắc cùng (chủ, đối tượng, loại) mà:
          - vẫn đang `pending` — chưa gửi cái cũ thì thêm cái mới làm gì, hoặc
          - vừa tạo trong vòng `repeat_every_days` ngày (không lặp thì tính là một lần duy nhất).

        Tra MỘT lần cho cả lô rồi lọc trong bộ nhớ. Hỏi từng ứng viên là N+1, mà lượt quét
        này chạy trên toàn bộ user của hệ thống.
        """
        if not candidates:
            return []

        clauses = []
        for c in candidates:
            window = c.rule.repeat_every_days
            # Không lặp → chặn vĩnh viễn bằng mốc rất xa. Dùng số ngày lớn thay vì bỏ hẳn
            # điều kiện để mọi nhánh đi chung một câu truy vấn.
            cutoff = datetime.now(UTC) - timedelta(days=window if window else 36500)
            clauses.append(
                and_(
                    ReminderModel.owner_user_id == c.owner_user_id,
                    ReminderModel.target_type == c.target_type,
                    ReminderModel.target_id == c.target_id,
                    ReminderModel.reminder_type == c.rule.rule_type,
                    or_(
                        ReminderModel.status == "pending",
                        ReminderModel.created_at >= cutoff,
                    ),
                )
            )

        rows = await self.db.execute(
            select(
                ReminderModel.owner_user_id,
                ReminderModel.target_type,
                ReminderModel.target_id,
                ReminderModel.reminder_type,
            ).where(or_(*clauses))
        )
        # Ép về tuple thường thay vì giữ `Row`: dưới kia mình `add` tuple tự dựng vào cùng
        # tập hợp này, mà trộn hai kiểu rồi trông cậy vào việc chúng băm giống nhau là chỗ
        # hỏng ngầm — chống trùng mà hỏng thì khách nhận email lặp.
        seen: set[tuple[uuid.UUID, str, uuid.UUID, str]] = {tuple(row) for row in rows.all()}  # type: ignore[misc]

        out: list[Candidate] = []
        for c in candidates:
            key = (c.owner_user_id, c.target_type, c.target_id, c.rule.rule_type)
            if key in seen:
                continue
            # Chặn trùng NGAY TRONG một lượt quét: hai hoá đơn cùng khách có thể sinh ra
            # hai ứng viên `re_engagement` giống hệt nhau mà chưa cái nào kịp vào DB.
            seen.add(key)
            out.append(c)
        return out

    # ------------------------------------------------------------------------------
    # Dựng lời nhắc
    # ------------------------------------------------------------------------------

    def _build_reminder(self, c: Candidate) -> ReminderModel:
        return ReminderModel(
            owner_user_id=c.owner_user_id,
            target_type=c.target_type,
            target_id=c.target_id,
            reminder_type=c.rule.rule_type,
            channel=c.rule.channel,
            status="pending",
            scheduled_at=self._scheduled_at(c.rule),
            message_preview=c.message,
            # Chưa bật "tự gửi" thì lời nhắc phải nằm im chờ người duyệt. `list_due()` lọc
            # đúng cột này — không có nó thì beat gửi thẳng cho khách.
            requires_approval=not c.rule.auto_send,
            created_by_rule=True,
        )

    async def _load_timezones(self) -> None:
        rows = await self.db.execute(
            select(UserModel.id, UserModel.timezone).join(
                ReminderRuleModel, ReminderRuleModel.owner_user_id == UserModel.id
            )
        )
        self._timezones = {user_id: tz for user_id, tz in rows.all()}

    def _scheduled_at(self, rule: ReminderRuleModel) -> datetime:
        """Hôm nay lúc `send_at_hour` theo giờ của người dùng; qua giờ rồi thì mai.

        KHÔNG hẹn vào đúng lúc quét: lượt quét chạy rạng sáng, không ai muốn nhận email
        công việc lúc 1 giờ sáng.
        """
        tz = self._user_tz(rule.owner_user_id)
        now = datetime.now(tz)
        target = now.replace(hour=rule.send_at_hour, minute=0, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return target.astimezone(UTC)

    def _today_for(self, owner_user_id: uuid.UUID) -> date:
        """Hôm nay theo lịch của NGƯỜI DÙNG, không phải theo UTC.

        Hạn thanh toán là một ngày trên tờ hoá đơn, người dùng đọc nó theo lịch của mình.
        Lấy `datetime.now(UTC).date()` thì từ 17h UTC trở đi khách Việt Nam đã sang ngày
        mới mà hệ thống vẫn nghĩ là hôm qua — lệch nguyên một ngày.  #Huynh
        """
        return self.today or datetime.now(self._user_tz(owner_user_id)).date()

    def _user_tz(self, owner_user_id: uuid.UUID) -> ZoneInfo:
        name = self._timezones.get(owner_user_id) or "Asia/Ho_Chi_Minh"
        try:
            return ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError):
            # Một múi giờ rác trong DB không được phép làm hỏng lượt quét của mọi user khác.
            return ZoneInfo("Asia/Ho_Chi_Minh")

    async def _notify_owners(self, created: list[Candidate]) -> None:
        """Gộp một thông báo cho mỗi người, không bắn từng cái một.

        Năm lời nhắc chờ duyệt mà reo năm tiếng chuông thì người dùng tắt thông báo luôn.
        """
        pending: dict[uuid.UUID, int] = {}
        for c in created:
            if not c.rule.auto_send:
                pending[c.owner_user_id] = pending.get(c.owner_user_id, 0) + 1

        notifications = NotificationService(db=self.db)
        for owner_user_id, count in pending.items():
            await notifications.notify(
                user_id=owner_user_id,
                type=TYPE_REMINDER_DRAFTED,
                title=f"{count} lời nhắc đang chờ bạn duyệt",
                body="SoloDesk đã soạn sẵn nội dung. Bạn xem lại rồi bấm Gửi ngay nhé.",
                entity_type="reminder",
                entity_id=None,
            )

    # ------------------------------------------------------------------------------
    # Phụ trợ
    # ------------------------------------------------------------------------------

    async def _join_rule(
        self,
        rule_type: RuleType,
        stmt: Any,
        owner_column: Any,
        extra: Any = None,
    ) -> list[Any]:
        """Chỉ lấy bản ghi của user đã BẬT quy tắc này.

        Nối bảng quy tắc ngay trong truy vấn thay vì lọc sau: user tắt quy tắc thì dữ liệu
        của họ không bao giờ rời khỏi database.
        """
        stmt = stmt.join(
            ReminderRuleModel,
            and_(
                ReminderRuleModel.owner_user_id == owner_column,
                ReminderRuleModel.rule_type == rule_type.value,
                ReminderRuleModel.is_enabled.is_(True),
            ),
        )
        if extra is not None:
            stmt = stmt.where(extra)
        return list((await self.db.execute(stmt)).all())

    @staticmethod
    def _render(
        rule_type: RuleType, rule: ReminderRuleModel, variables: dict[str, str]
    ) -> str:
        """Soạn nội dung lời nhắc từ template tự soạn của freelancer (hoặc mặc định)."""
        template = effective_template(rule_type, rule.message_template)
        return render_reminder_template(template, variables)

    def _invoice_candidate(
        self, invoice: Any, client_name: str, rule: ReminderRuleModel, *, message: str
    ) -> Candidate:
        return Candidate(
            owner_user_id=invoice.owner_user_id,
            target_type="invoice",
            target_id=invoice.id,
            rule=rule,
            client_name=client_name,
            message=message,
        )

    def _is_older_than(self, moment: datetime | None, days: int) -> bool:
        if moment is None:
            return False
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)
        return moment <= datetime.now(UTC) - timedelta(days=days)

    @staticmethod
    def _vn_date(value: date) -> str:
        return f"{value.day:02d}/{value.month:02d}/{value.year}"

    @staticmethod
    def _money(invoice: Any) -> str:
        """Số tiền CÒN LẠI, không phải tổng hoá đơn.

        Khách trả một phần rồi mà nhắc nguyên tổng thì thành đòi thừa tiền — cách tính này
        giống `FollowUpService._load_context`.
        """
        remaining = (invoice.total or 0) - (invoice.amount_paid or 0)
        formatted = f"{float(remaining):,.0f}".replace(",", ".")
        currency = invoice.currency or "VND"
        return f"{formatted} ₫" if currency == "VND" else f"{formatted} {currency}"
