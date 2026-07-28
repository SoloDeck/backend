"""Gửi lời nhắc đi THẬT — email cho khách, thông báo trong ứng dụng cho freelancer.

Trước file này, `send_reminder` là `raise NotImplementedError`: freelancer đặt lịch nhắc
xong thì nó nằm im mãi ở `pending`, hai trạng thái `sent`/`failed` trong enum chưa bao giờ
xảy ra. Y hệt vết `mark_overdue_invoices` — enum có sẵn chỗ, chỉ là chưa ai viết phần điền
vào.

Nghiệp vụ gửi nằm ở đây chứ KHÔNG nằm trong Celery task, vì hai chỗ cần nó:
worker (nhắc theo lịch) và endpoint `POST /reminders/{id}/send` (bấm "Gửi ngay"). Một
đường code cho cả hai thì không có nhánh thứ hai để lệch — và test được bằng AsyncMock.
#Huynh
"""

import re
import smtplib
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from html import escape
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import settings
from src.infrastructure.storage.object_storage import object_storage
from src.integrations.zalo.client import (
    ZaloOAClient,
    ZaloPermanentError,
    ZaloTransientError,
    get_zalo_client,
)
from src.modules.notifications.application.service import NotificationService
from src.modules.reminders.application.attachments import (
    images_html,
    load_image_bytes,
    parse_attachments,
)
from src.modules.reminders.application.payment_block import build_payment_section
from src.modules.reminders.infrastructure.repository import RemindersRepository
from src.shared.email.smtp import send_email as smtp_send_email
from src.shared.exceptions.domain import NotFoundError

log = structlog.get_logger(__name__)

# Khớp CHECK constraint `chk_reminders_retry` (retry_count BETWEEN 0 AND 3) và NFR của
# Phiếu: thử tối đa 3 lần rồi mới báo lỗi cho người dùng.
MAX_DELIVERY_ATTEMPTS = 3


class DeliveryError(Exception):
    """Không gửi được. Câu chữ trong exception là để NGƯỜI DÙNG đọc, nên viết tiếng Việt."""


class TransientDeliveryError(DeliveryError):
    """Lỗi có khả năng tự khỏi (mail server chập chờn, mất mạng) → đáng thử lại."""


class PermanentDeliveryError(DeliveryError):
    """Thử lại bao nhiêu lần cũng vậy (khách chưa có email) → báo ngay, đừng bắt chờ."""


@dataclass(frozen=True)
class DeliveryResult:
    """Kết quả một lượt gửi, đủ để worker quyết định retry và để API trả lời người dùng."""

    status: str
    """Trạng thái mới của reminder: sent / failed / skipped / pending (đang chờ thử lại)."""

    detail: str
    """Một câu tiếng Việt giải thích chuyện gì đã xảy ra — hiện thẳng lên giao diện."""

    delivered: bool = False
    should_retry: bool = False


# ---------------------------------------------------------------------------------
# Soạn nội dung — hàm thuần, test được không cần database
# ---------------------------------------------------------------------------------

# Tiêu đề thư. Mỗi loại nhắc có hai bản: có tên dự án/hoá đơn và không có (khách hàng có
# thể chưa gắn với deal nào). Ghép sẵn ở đây thay vì để AI đặt tiêu đề — tiêu đề là thứ
# khách nhìn thấy đầu tiên, không nên để nó bịa.
_SUBJECTS: dict[str, tuple[str, str]] = {
    "follow_up": ("Hỏi thăm về {label}", "Hỏi thăm về dự án của mình"),
    "proposal_follow_up": ("Về báo giá {label}", "Về báo giá đã gửi"),
    "contract_signing_nudge": ("Về hợp đồng {label}", "Về hợp đồng đang chờ ký"),
    "payment_due": ("Nhắc thanh toán {label}", "Nhắc thanh toán sắp đến hạn"),
    "payment_overdue": ("Hoá đơn {label} đã quá hạn", "Hoá đơn đã quá hạn thanh toán"),
    "re_engagement": ("Lâu rồi chưa liên lạc — về {label}", "Lâu rồi chưa liên lạc"),
    "custom": ("Về {label}", "Lời nhắn từ SoloDesk"),
}


def build_subject(reminder_type: str, label: str | None) -> str:
    """Tiêu đề thư gửi KHÁCH.

    Cố ý KHÔNG gắn tiền tố "[SoloDesk]" như thư OTP: thư này là freelancer nhắn cho khách
    của mình, không phải hệ thống thông báo. Gắn tên phần mềm vào là lộ ra rằng máy gửi.
    """
    with_label, without_label = _SUBJECTS.get(reminder_type, _SUBJECTS["custom"])
    label = (label or "").strip()
    return with_label.format(label=label) if label else without_label


def build_body(
    message: str,
    sender_name: str | None,
    sender_email: str | None = None,
    project_label: str | None = None,
    payment_html: str = "",
    payment_plain: str = "",
) -> tuple[str, str]:
    """Trả về (html, plain) từ nội dung người dùng đã duyệt.

    Bắt buộc `escape()`: nội dung do AI soạn và người dùng sửa tay, chỉ cần một dấu `&`
    hay `<` là vỡ HTML của thư gửi khách.

    `payment_*` là khối "Thanh toán cho tôi" (QR + số tài khoản), chèn SAU nội dung và
    TRƯỚC chữ ký — đọc xong lời nhắn là thấy ngay cách trả tiền, không phải cuộn tìm.
    """
    message = message.strip()
    blocks = [block.strip() for block in re.split(r"\n\s*\n", message) if block.strip()]
    html_blocks = [f"<p>{escape(block).replace(chr(10), '<br>')}</p>" for block in blocks]

    if payment_html:
        # KHÔNG escape: khối này do chính hệ thống dựng (payment_block.py), và bên trong đó
        # mọi giá trị người dùng nhập đều đã được escape rồi.
        html_blocks.append(payment_html)
        message = f"{message}\n\n{payment_plain}"

    signature = (sender_name or "").strip()
    if signature:
        html_blocks.append(f"<p>—<br>{escape(signature)}</p>")
        message = f"{message}\n\n—\n{signature}"

    footer = build_footer(sender_name, sender_email, project_label)
    if footer:
        html_blocks.append(
            '<hr style="border:0;border-top:1px solid #e5e7eb;margin:24px 0 12px">'
            f'<p style="color:#6b7280;font-size:12px;line-height:1.6">'
            f"{escape(footer).replace(chr(10), '<br>')}</p>"
        )
        message = f"{message}\n\n---\n{footer}"

    return "".join(html_blocks), message


def build_footer(
    sender_name: str | None,
    sender_email: str | None,
    project_label: str | None,
) -> str:
    """Chân thư nói rõ AI gửi, VỀ VIỆC GÌ, và trả lời thì về đâu.

    Địa chỉ `From` buộc phải là hộp thư của SoloDesk (xem `smtp.py` — khai địa chỉ
    freelancer là mạo danh, thư rơi vào spam). Nên khách nhìn vào chỉ thấy
    `solodeskai@gmail.com` và không biết đó là ai.

    Chân thư này bù đúng chỗ đó: nêu tên freelancer, **địa chỉ email THẬT của họ để khách
    lưu lại**, và dự án đang nói tới. Không có nó thì khách nhận một cái thư từ địa chỉ lạ,
    nội dung trống trơn ngữ cảnh — trông y như thư rác.  #Huynh
    """
    name = (sender_name or "").strip()
    if not name:
        return ""

    who = f"{name} ({sender_email.strip()})" if (sender_email or "").strip() else name
    lines = [f"Email này được gửi từ {who} qua SoloDesk."]

    project = (project_label or "").strip()
    if project:
        lines.append(f"Về dự án: {project}.")

    if (sender_email or "").strip():
        lines.append(f"Bạn trả lời email này, thư sẽ về thẳng hộp thư của {name}.")

    return "\n".join(lines)


def is_retryable_smtp_error(exc: Exception) -> bool:
    """Lỗi SMTP nào đáng thử lại?

    Địa chỉ sai hay sai mật khẩu ứng dụng thì thử mười lần cũng thế — báo ngay còn hơn
    bắt người dùng đợi ba lượt retry rồi mới biết.
    """
    permanent = (
        smtplib.SMTPRecipientsRefused,
        smtplib.SMTPSenderRefused,
        smtplib.SMTPAuthenticationError,
        smtplib.SMTPNotSupportedError,
    )
    return not isinstance(exc, permanent)


# ---------------------------------------------------------------------------------
# Nghiệp vụ gửi
# ---------------------------------------------------------------------------------


@dataclass
class ReminderDeliveryService:
    db: AsyncSession
    # `send_email` là tham số chứ không phải import cứng, để test bơm hàm giả vào —
    # cùng lối với việc tiêm file store thay vì dùng singleton ở deals.
    #
    # Mặc định để `None` rồi tra ở `__post_init__` chứ KHÔNG gán thẳng `smtp_send_email`:
    # dataclass nướng giá trị mặc định vào chữ ký `__init__` ngay lúc định nghĩa lớp, nên
    # gán thẳng thì integration test có patch module cũng không đổi được — và test sẽ gửi
    # email thật.  #Huynh
    send_email: Callable[..., Awaitable[None]] | None = None
    repo: RemindersRepository | None = None
    # Tiêm giống send_email: test bơm mock, còn chạy thật thì chọn real/mock theo config.
    zalo_client: ZaloOAClient | None = None

    def __post_init__(self) -> None:
        if self.repo is None:
            self.repo = RemindersRepository(self.db)
        if self.send_email is None:
            self.send_email = smtp_send_email
        if self.zalo_client is None:
            self.zalo_client = get_zalo_client(settings)

    async def deliver(self, reminder_id: uuid.UUID, *, unattended: bool = True) -> DeliveryResult:
        """Gửi một lời nhắc.

        `unattended` = không có ai ngồi trước máy chờ kết quả (worker chạy theo lịch).
        Worker để mặc định True; endpoint "Gửi ngay" truyền False vì người dùng vừa bấm
        nút và đã thấy kết quả hiện ra ngay — bắn thêm thông báo vào chuông chỉ là nhiễu.
        """
        assert self.repo is not None
        reminder = await self.repo.get_for_delivery(reminder_id)
        if reminder is None:
            raise NotFoundError(f"Reminder {reminder_id} not found")

        # Chốt chặn quan trọng nhất của cả file: chỉ reminder đang chờ mới được gửi. Kết
        # hợp với khoá hàng ở `get_for_delivery`, đây là thứ bảo đảm khách không nhận hai
        # lần cùng một lời nhắc khi worker và người dùng bấm "Gửi ngay" trùng nhau.
        if reminder.status != "pending":
            return DeliveryResult(
                status=reminder.status,
                detail="Lời nhắc này không còn ở trạng thái chờ gửi.",
            )

        try:
            detail = await self._dispatch(reminder, unattended=unattended)
        except PermanentDeliveryError as exc:
            return await self._give_up(reminder, str(exc))
        except TransientDeliveryError as exc:
            return await self._maybe_retry(reminder, str(exc))

        reminder.status = "sent"
        await self.repo.add_delivery_record(
            reminder_id=reminder.id,
            channel=reminder.channel,
            outcome="success",
            error_message=None,
        )
        await self.db.flush()
        log.info("reminder.sent", reminder_id=str(reminder.id), channel=reminder.channel)
        return DeliveryResult(status="sent", detail=detail, delivered=True)

    # --- Từng kênh -----------------------------------------------------------------

    async def _dispatch(self, reminder: Any, *, unattended: bool) -> str:
        if reminder.channel == "in_app":
            # Ở kênh này thông báo CHÍNH LÀ việc gửi — không có thư nào rời hệ thống cả.
            # Nên nó luôn phải chạy, kể cả khi người dùng tự bấm "Gửi ngay"; bỏ qua là
            # lời nhắc không làm gì hết.
            client, _ = await self._target(reminder)
            await self._notify_due(reminder, client)
            return "Đã nhắc bạn trong ứng dụng."

        if reminder.channel == "zalo":
            return await self._send_zalo(reminder, unattended=unattended)

        # "email" và "both" đều gửi thư thật cho khách.
        client, _ = await self._target(reminder)
        detail = await self._send_to_client(reminder)

        # Biên nhận "đã gửi rồi đấy". Chỉ bắn khi hệ thống tự làm lúc người dùng vắng mặt:
        # bấm "Gửi ngay" xong thấy toast báo kết quả rồi mà chuông lại kêu nữa thì phiền.
        # Kênh "both" là người dùng CHỦ ĐỘNG xin được ghi lại trong app nên luôn bắn.
        if unattended or reminder.channel == "both":
            await NotificationService(db=self.db).notify_reminder_sent(
                owner_user_id=reminder.owner_user_id,
                reminder_id=reminder.id,
                client_name=client.name if client else None,
                recipient=(client.email or "").strip() if client else "",
            )
            if reminder.channel == "both":
                detail = f"{detail} Đồng thời đã ghi lại thông báo cho bạn."
        return detail

    async def _send_to_client(self, reminder: Any) -> str:
        message = (reminder.message_preview or "").strip()
        if not message:
            # Thà không gửi còn hơn gửi cho khách một cái thư trắng.
            raise PermanentDeliveryError("Lời nhắc chưa có nội dung nên không thể gửi.")

        client, label = await self._target(reminder)
        if client is None:
            raise PermanentDeliveryError(
                "Không tìm thấy khách hàng của lời nhắc này — có thể dữ liệu đã bị xoá."
            )

        recipient = (client.email or "").strip()
        if not recipient:
            raise PermanentDeliveryError(
                f"Khách {client.name} chưa có email. Bổ sung email rồi gửi lại giúp bạn nhé."
            )

        assert self.repo is not None
        owner = await self.repo.get_owner(reminder.owner_user_id)
        payment_html, payment_plain, qr_png = await build_payment_section(
            self.db, reminder, owner, label
        )

        # Ảnh freelancer chèn (mã QR chụp sẵn, ảnh sản phẩm…) — nhúng bằng `cid:` để hiện
        # ngay trong thân thư, không rơi xuống cuối dạng cục tải về.  #Huynh
        images = parse_attachments(getattr(reminder, "attachments", None))
        image_bytes = await load_image_bytes(object_storage, images) if images else {}
        payment_html = (
            images_html(images, {cid: f"cid:{cid}" for cid in image_bytes}) + payment_html
        )

        inline: dict[str, bytes] = dict(image_bytes)
        if qr_png:
            inline["vietqr"] = qr_png

        html, plain = build_body(
            message,
            owner.full_name if owner else None,
            owner.email if owner else None,
            label,
            payment_html=payment_html,
            payment_plain=payment_plain,
        )

        assert self.send_email is not None
        try:
            await self.send_email(
                to=recipient,
                subject=build_subject(reminder.reminder_type, label),
                html=html,
                plain=plain,
                inline_images=inline or None,
                # Thư này là FREELANCER nhắn cho khách của họ — SoloDesk chỉ soạn hộ và
                # bấm gửi hộ. Khách phải thấy tên freelancer, và bấm "Trả lời" là thư về
                # thẳng hộp thư freelancer chứ không rơi vào hòm thư của SoloDesk.  #Huynh
                from_name=owner.full_name if owner else None,
                reply_to=owner.email if owner else None,
            )
        except Exception as exc:
            if is_retryable_smtp_error(exc):
                raise TransientDeliveryError(
                    "Máy chủ email đang không phản hồi. Hệ thống sẽ tự thử lại."
                ) from exc
            raise PermanentDeliveryError(
                f"Máy chủ email từ chối gửi tới {recipient}. Kiểm tra lại địa chỉ giúp bạn nhé."
            ) from exc

        return f"Đã gửi email cho {client.name} ({recipient})."

    async def _send_zalo(self, reminder: Any, *, unattended: bool) -> str:
        """Gửi tin CS qua Zalo OA của freelancer tới follower là khách.

        Trước đây kênh này chỉ `_skip_zalo` (đánh dấu skipped) vì chưa nối được OA. Giờ đã có
        luồng kết nối: gửi THẬT, cùng khuôn với email — trả câu mô tả khi xong, ném
        Transient/Permanent để deliver() lo retry ≤3 / bỏ cuộc. Vẫn KHÔNG giả "đã gửi": chưa
        kết nối OA hay khách chưa follow thì báo thẳng bằng PermanentDeliveryError.  #Huynh
        """
        message = (reminder.message_preview or "").strip()
        if not message:
            raise PermanentDeliveryError("Lời nhắc chưa có nội dung nên không thể gửi.")

        client, _ = await self._target(reminder)
        if client is None:
            raise PermanentDeliveryError(
                "Không tìm thấy khách hàng của lời nhắc này — có thể dữ liệu đã bị xoá."
            )

        assert self.repo is not None
        owner = await self.repo.get_owner(reminder.owner_user_id)
        access_token = (getattr(owner, "zalo_oa_access_token", None) or "").strip()
        if not access_token:
            raise PermanentDeliveryError(
                "Bạn chưa kết nối Zalo OA. Vào Cài đặt để kết nối rồi gửi lại giúp nhé."
            )

        user_id = (getattr(client, "zalo_user_id", None) or "").strip()
        if not user_id:
            if settings.zalo_mode == "mock":
                # Mock: gán tạm để luồng chạy trọn local khi chưa có webhook thật.
                user_id = f"mock-user-{str(getattr(client, 'id', '') or '0')[:8]}"
                client.zalo_user_id = user_id
            else:
                raise PermanentDeliveryError(
                    f"Khách {client.name} chưa kết nối Zalo với OA của bạn. Nhắn Zalo tay giúp nhé."
                )

        assert self.zalo_client is not None
        try:
            await self.zalo_client.send_cs_message(
                access_token=access_token, user_id=user_id, text=message
            )
        except ZaloTransientError as exc:
            raise TransientDeliveryError(str(exc)) from exc
        except ZaloPermanentError as exc:
            raise PermanentDeliveryError(str(exc)) from exc

        # Biên nhận trong app khi hệ thống tự gửi lúc người dùng vắng mặt (như kênh email).
        if unattended:
            await NotificationService(db=self.db).notify_reminder_sent(
                owner_user_id=reminder.owner_user_id,
                reminder_id=reminder.id,
                client_name=client.name if client else None,
                recipient="Zalo",
            )
        return f"Đã gửi tin Zalo cho {client.name}."

    # --- Xử lý hỏng ----------------------------------------------------------------

    async def _maybe_retry(self, reminder: Any, reason: str) -> DeliveryResult:
        assert self.repo is not None
        reminder.retry_count = (reminder.retry_count or 0) + 1
        await self.repo.add_delivery_record(
            reminder_id=reminder.id,
            channel=reminder.channel,
            outcome="failure",
            error_message=reason,
        )

        if reminder.retry_count >= MAX_DELIVERY_ATTEMPTS:
            return await self._give_up(
                reminder,
                f"Đã thử gửi {MAX_DELIVERY_ATTEMPTS} lần nhưng không thành công. {reason}",
                record=False,
            )

        # Vẫn để `pending` để lượt retry sau còn gửi được.
        await self.db.flush()
        log.warning(
            "reminder.delivery_retry",
            reminder_id=str(reminder.id),
            attempt=reminder.retry_count,
            reason=reason,
        )
        return DeliveryResult(status="pending", detail=reason, should_retry=True)

    async def _give_up(self, reminder: Any, reason: str, *, record: bool = True) -> DeliveryResult:
        assert self.repo is not None
        reminder.status = "failed"
        if record:
            await self.repo.add_delivery_record(
                reminder_id=reminder.id,
                channel=reminder.channel,
                outcome="failure",
                error_message=reason,
            )

        client, _ = await self._target(reminder)
        await NotificationService(db=self.db).notify_reminder_failed(
            owner_user_id=reminder.owner_user_id,
            reminder_id=reminder.id,
            client_name=client.name if client else None,
            reason=reason,
        )
        await self.db.flush()
        log.warning("reminder.delivery_failed", reminder_id=str(reminder.id), reason=reason)
        return DeliveryResult(status="failed", detail=reason)

    # --- Phụ trợ -------------------------------------------------------------------

    async def _target(self, reminder: Any) -> tuple[Any, str | None]:
        assert self.repo is not None
        return await self.repo.resolve_target(
            target_type=reminder.target_type,
            target_id=reminder.target_id,
            owner_user_id=reminder.owner_user_id,
        )

    async def _notify_due(self, reminder: Any, client: Any) -> None:
        await NotificationService(db=self.db).notify_reminder_due(
            owner_user_id=reminder.owner_user_id,
            reminder_id=reminder.id,
            client_name=client.name if client else None,
            message_preview=reminder.message_preview,
        )
