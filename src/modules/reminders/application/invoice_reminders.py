"""Lời nhắc thanh toán TỰ ĐẶT khi gửi hóa đơn, theo đúng quy tắc "Nhắc trước khi hóa đơn tới hạn".

Quy tắc có sẵn (`RuleType.PAYMENT_DUE`, chỉnh ở Cài đặt hồ sơ → Nhắc nhở tự động) chỉ tạo lời nhắc
vào ĐÚNG ngày (hạn − N ngày), nên freelancer gửi hóa đơn xong mở tab Nhắc nhở ra thì chưa thấy gì.
Hàm ở đây đặt sẵn lời nhắc đó NGAY LÚC GỬI HÓA ĐƠN, để nó nằm trong tab từ đầu — xem, sửa nội dung,
đổi giờ, "Gửi ngay" hay "Hủy" đều được.

Mọi thứ lấy từ chính quy tắc đó, không có luật riêng: số ngày (`offset_days`), giờ gửi, kênh,
nội dung mẫu, và công tắc bật/tắt. Tắt quy tắc thì gửi hóa đơn cũng không đặt lời nhắc. Lời nhắc
luôn nằm CHỜ freelancer duyệt (quy tắc không còn công tắc "tự gửi"). Nó mang loại `payment_due`
nên khoá chống trùng của bộ quét hằng ngày sẽ không đẻ thêm một lời nhắc "đến hạn" thứ hai cho
cùng hóa đơn.

Hạn thanh toán còn quá gần thì KHÔNG đặt. Luật tính theo NGÀY (lịch của người dùng), không theo
giờ trong ngày: ngày nhắc (hạn − N ngày) phải nằm SAU ngày gửi hóa đơn — nhắc khách ngay trong ngày
vừa gửi hóa đơn cho họ thì vô nghĩa.

Lời nhắc chỉ có nghĩa khi hóa đơn CHƯA được ghi nhận thanh toán, nên có các lớp bảo vệ:

- ghi nhận đã thu đủ (hoặc hủy) hóa đơn thì lời nhắc đang chờ bị hủy ngay
  (`retire_invoice_payment_reminders`);
- thu một phần thì số tiền ghi trong chữ được cập nhật theo (`refresh_invoice_reminder_amounts`),
  vì lời nhắc đặt từ sớm mà số còn nợ đã khác;
- tới giờ gửi mà hóa đơn vẫn đã trả/đã hủy (do đường nào đó không đi qua các bước trên) thì khâu
  giao thư bỏ qua (`invoice_is_settled`) — thà không gửi còn hơn nhắc khách trả lại.  #Huynh
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import structlog
from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import DealModel, InvoiceModel, ReminderModel
from src.modules.reminders.application.auto_scheduler import AutoReminderScheduler
from src.modules.reminders.application.payment_block import PAYMENT_REMINDER_TYPES
from src.modules.reminders.application.rule_service import ReminderRulesService
from src.modules.reminders.domain.value_objects.reminder_rules import (
    RuleType,
    effective_template,
    render_reminder_template,
)
from src.modules.reminders.infrastructure.repository import RemindersRepository

log = structlog.get_logger(__name__)

# Hóa đơn ở các trạng thái này thì không còn gì để nhắc thanh toán.
SETTLED_INVOICE_STATUSES = frozenset({"paid", "void"})

# Vì sao KHÔNG đặt được lời nhắc — web dựa vào đây để nói đúng cho người dùng.
REASON_DISABLED = "disabled"  # freelancer đã tắt quy tắc "Nhắc trước khi hóa đơn tới hạn"
REASON_TOO_SOON = "too_soon"  # hạn thanh toán quá gần, ngày nhắc không nằm sau ngày gửi
REASON_NO_CLIENT_EMAIL = "no_client_email"  # kênh gửi cho khách mà khách chưa có email
REASON_ERROR = "error"  # lỗi DB (đã được nuốt để không làm hỏng việc gửi hóa đơn)


@dataclass(frozen=True)
class PaymentReminderOutcome:
    """Kết quả của việc đặt lời nhắc: đặt được (kèm lời nhắc) hoặc vì sao không đặt."""

    reminder: ReminderModel | None = None
    reason: str | None = None
    days_before_due: int | None = None
    requires_approval: bool = False

    def as_response(self) -> dict[str, Any]:
        """Dạng nhúng vào phản hồi của lệnh gửi hóa đơn (`InvoiceResponse.payment_reminder`)."""
        return {
            "scheduled": self.reminder is not None,
            "scheduled_at": self.reminder.scheduled_at if self.reminder is not None else None,
            "days_before_due": self.days_before_due,
            "requires_approval": self.requires_approval,
            "reason": self.reason,
        }


def _zone(tz_name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name or "Asia/Ho_Chi_Minh")
    except (ZoneInfoNotFoundError, ValueError):
        # Múi giờ rác trong DB không được phép làm hỏng việc gửi hóa đơn.
        return ZoneInfo("Asia/Ho_Chi_Minh")


def reminder_time_before_due(
    due_date: date, days: int, tz_name: str | None, *, hour: int = 9
) -> datetime:
    """`hour` giờ của ngày cách hạn thanh toán `days` ngày, theo giờ NGƯỜI DÙNG, đổi về UTC.

    Hạn thanh toán là một NGÀY trên tờ hóa đơn, người dùng đọc nó theo lịch của mình — nên "N ngày
    trước hạn" cũng tính theo lịch của họ, không theo UTC.
    """
    local = datetime.combine(due_date - timedelta(days=days), time(hour), tzinfo=_zone(tz_name))
    return local.astimezone(UTC)


def remaining_amount_text(invoice: Any) -> str:
    """Số tiền CÒN LẠI của hóa đơn dạng "50.000.000 ₫" — cùng cách ghi với bộ quét hằng ngày."""
    return AutoReminderScheduler._money(invoice)


async def schedule_invoice_payment_reminder(
    db: AsyncSession,
    *,
    invoice: Any,
    client: Any,
    owner: Any,
    now: datetime | None = None,
) -> PaymentReminderOutcome:
    """Đặt lời nhắc thanh toán cho `invoice` theo quy tắc "tới hạn" của chủ hóa đơn.

    KHÔNG BAO GIỜ làm hỏng việc gửi hóa đơn: thư hóa đơn đã rời máy chủ trước khi hàm này chạy, nên
    lỗi DB ở đây chỉ được ghi log chứ không ném ra. Cả phần đọc quy tắc lẫn phần ghi nằm trong
    SAVEPOINT để một lỗi không kéo theo việc mất luôn trạng thái "đã gửi" của hóa đơn.
    """
    try:
        async with db.begin_nested():
            return await _schedule(db, invoice=invoice, client=client, owner=owner, now=now)
    except SQLAlchemyError as exc:
        log.warning("invoice_reminder.create_failed", invoice_id=str(invoice.id), error=str(exc))
        return PaymentReminderOutcome(reason=REASON_ERROR)


async def _schedule(
    db: AsyncSession, *, invoice: Any, client: Any, owner: Any, now: datetime | None
) -> PaymentReminderOutcome:
    rules = await ReminderRulesService(db=db).list_for_user(invoice.owner_user_id)
    rule = next((r for r in rules if r.rule_type == RuleType.PAYMENT_DUE.value), None)
    if rule is None or not rule.is_enabled:
        return PaymentReminderOutcome(reason=REASON_DISABLED)

    days = int(rule.offset_days)
    # Quy tắc không còn công tắc "tự gửi": lời nhắc do quy tắc tạo luôn chờ freelancer duyệt.
    requires_approval = True
    context = {"days_before_due": days, "requires_approval": requires_approval}

    # Kênh gửi cho khách mà khách không có email thì lời nhắc chỉ hỏng ngay lúc tới giờ.
    email = (getattr(client, "email", None) or "").strip()
    if rule.channel in ("email", "both") and not email:
        log.info("invoice_reminder.skipped_no_client_email", invoice_id=str(invoice.id))
        return PaymentReminderOutcome(reason=REASON_NO_CLIENT_EMAIL, **context)

    tz_name = getattr(owner, "timezone", None)
    # So theo NGÀY LỊCH của người dùng chứ không so giờ: kết quả không được đổi theo việc gửi hóa
    # đơn lúc 8h hay 10h sáng. Ngày nhắc phải sau hôm nay.
    today = (now or datetime.now(UTC)).astimezone(_zone(tz_name)).date()
    if invoice.due_date - timedelta(days=days) <= today:
        log.info("invoice_reminder.skipped_due_too_soon", invoice_id=str(invoice.id))
        return PaymentReminderOutcome(reason=REASON_TOO_SOON, **context)

    message = render_reminder_template(
        effective_template(RuleType.PAYMENT_DUE, rule.message_template),
        {
            "client_name": getattr(client, "name", "") or "",
            "invoice_number": invoice.invoice_number,
            "due_date": f"{invoice.due_date:%d/%m/%Y}",
            "amount": remaining_amount_text(invoice),
        },
    )
    reminder = await RemindersRepository(db).create(
        owner_user_id=invoice.owner_user_id,
        target_type="invoice",
        target_id=invoice.id,
        reminder_type=RuleType.PAYMENT_DUE.value,
        channel=rule.channel,
        status="pending",
        scheduled_at=reminder_time_before_due(
            invoice.due_date, days, tz_name, hour=int(rule.send_at_hour)
        ),
        message_preview=message,
        # Nằm chờ freelancer duyệt ở tab Nhắc nhở, y như lời nhắc do bộ quét hằng ngày tạo.
        requires_approval=requires_approval,
        # Để tab Nhắc nhở gắn nhãn "Tự động" — phân biệt với lời nhắc tự đặt tay.
        created_by_rule=True,
    )
    return PaymentReminderOutcome(reminder=reminder, **context)


async def retire_invoice_payment_reminders(
    db: AsyncSession, *, owner_user_id: uuid.UUID, invoice_id: uuid.UUID
) -> int:
    """Hủy các lời nhắc THANH TOÁN đang chờ của một hóa đơn vừa thu đủ hoặc vừa bị hủy.

    Chỉ đụng lời nhắc loại thanh toán: lời nhắc hỏi thăm do freelancer tự soạn cho hóa đơn đó (nếu
    có) vẫn là ý của họ. Trả số lời nhắc đã hủy.
    """
    result = await db.execute(
        update(ReminderModel)
        .where(
            ReminderModel.owner_user_id == owner_user_id,
            ReminderModel.target_type == "invoice",
            ReminderModel.target_id == invoice_id,
            ReminderModel.status == "pending",
            ReminderModel.reminder_type.in_(PAYMENT_REMINDER_TYPES),
        )
        .values(status="cancelled")
    )
    return int(result.rowcount or 0)


async def refresh_invoice_reminder_amounts(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    invoice_id: uuid.UUID,
    old_text: str,
    new_text: str,
) -> int:
    """Đổi số tiền cũ thành số mới trong chữ của các lời nhắc thanh toán đang chờ.

    Lời nhắc đặt từ lúc gửi hóa đơn nên có thể chờ nhiều ngày; khách trả một phần trong thời gian đó
    thì chữ "số tiền còn lại 50.000.000 ₫" đã cũ, lệch với mã QR (luôn tính số còn nợ lúc gửi). Chỉ
    thay đúng chuỗi số tiền cũ nên chữ freelancer đã tự sửa không bị đụng tới. Trả số lời nhắc đổi.
    """
    if not old_text or old_text == new_text:
        return 0
    result = await db.execute(
        select(ReminderModel).where(
            ReminderModel.owner_user_id == owner_user_id,
            ReminderModel.target_type == "invoice",
            ReminderModel.target_id == invoice_id,
            ReminderModel.status == "pending",
            ReminderModel.reminder_type.in_(PAYMENT_REMINDER_TYPES),
        )
    )
    changed = 0
    for reminder in result.scalars().all():
        if reminder.message_preview and old_text in reminder.message_preview:
            reminder.message_preview = reminder.message_preview.replace(old_text, new_text)
            changed += 1
    if changed:
        await db.flush()
    return changed


async def invoice_is_settled(db: AsyncSession, reminder: Any) -> bool:
    """Lời nhắc thanh toán này trỏ vào một hóa đơn đã thu đủ / đã hủy?

    Chỉ áp cho lời nhắc LOẠI THANH TOÁN nhắm vào hóa đơn; mọi lời nhắc khác trả `False`.
    """
    if (
        getattr(reminder, "target_type", None) != "invoice"
        or getattr(reminder, "reminder_type", None) not in PAYMENT_REMINDER_TYPES
    ):
        return False
    status = await db.scalar(
        select(InvoiceModel.status).where(
            InvoiceModel.id == reminder.target_id,
            InvoiceModel.owner_user_id == reminder.owner_user_id,
        )
    )
    return status in SETTLED_INVOICE_STATUSES


async def project_label_for(db: AsyncSession, reminder: Any, label: str | None) -> str | None:
    """Nhãn cho dòng "Về dự án: …" ở chân thư.

    Lời nhắc nhắm vào HÓA ĐƠN có nhãn là mã hóa đơn (dùng cho tiêu đề thư), nhưng chân thư nói về
    DỰ ÁN — để nguyên thì khách đọc "Về dự án: INV-2026…". Với hóa đơn thì lấy tên deal của nó;
    không tra được thì giữ nhãn cũ.
    """
    if getattr(reminder, "target_type", None) != "invoice":
        return label
    title = await db.scalar(
        select(DealModel.title)
        .join(InvoiceModel, InvoiceModel.deal_id == DealModel.id)
        .where(
            InvoiceModel.id == reminder.target_id,
            InvoiceModel.owner_user_id == reminder.owner_user_id,
            DealModel.deleted_at.is_(None),
        )
    )
    return title.strip() if isinstance(title, str) and title.strip() else label
