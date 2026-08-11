"""Async SMTP email sender.

Thin wrapper around Python's ``smtplib`` executed in a thread pool so it
does not block the event loop.
"""

import asyncio
import smtplib
import socket
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from functools import partial

import structlog

from src.config.settings import settings
from src.shared.exceptions.domain import EmailDeliveryError

logger = structlog.get_logger(__name__)

# Câu hiện cho NGƯỜI DÙNG. Cố ý không nêu host, cổng hay tài khoản — người dùng cuối không
# làm gì được với thông tin đó, còn kẻ dò thì có. Chi tiết thật nằm ở log.
#
# Điều duy nhất ba câu này phải làm cho bằng được: nói đúng việc người đọc NÊN LÀM TIẾP.
# Câu cũ gộp tất cả thành "thử lại sau ít phút" — với lỗi `auth` thì đó là lời khuyên sai,
# vì thử lại một nghìn lần cũng vậy.  #Huynh
_MSG_AUTH = (
    "Hộp thư hệ thống đang bị từ chối đăng nhập nên chưa gửi được email. "
    "Đây là lỗi cấu hình phía chúng tôi — thử lại cũng chưa gửi được, "
    "vui lòng báo quản trị viên."
)
_MSG_QUOTA = (
    "Hộp thư hệ thống đã chạm giới hạn gửi trong ngày. Vui lòng thử lại sau vài giờ."
)
_MSG_CONNECT = "Không kết nối được tới máy chủ thư. Vui lòng thử lại sau ít phút."
_MSG_UNKNOWN = "Chưa gửi được email do lỗi hệ thống thư. Vui lòng thử lại sau ít phút."

# Gmail báo quá hạn mức bằng `550 5.4.5 Daily user sending limit exceeded`, nhưng gói nó
# vào lớp ngoại lệ nào thì tuỳ bước gửi hỏng (DATA / RCPT / MAIL FROM). Nên nhận diện bằng
# NỘI DUNG câu trả lời của máy chủ, không bằng lớp ngoại lệ.
_QUOTA_MARKERS = (
    "5.4.5",
    "daily user sending limit",
    "sending limit exceeded",
    "quota",
    "rate limit",
    "too many messages",
)


def _server_reply_text(exc: BaseException) -> str:
    """Gom mọi mẩu văn bản máy chủ thư trả về trong một ngoại lệ smtplib."""
    parts = [str(exc)]
    raw = getattr(exc, "smtp_error", None)
    if isinstance(raw, bytes | bytearray):
        parts.append(bytes(raw).decode("utf-8", "replace"))
    elif raw:
        parts.append(str(raw))
    # SMTPRecipientsRefused gói lý do theo từng người nhận, không có `smtp_error`.
    recipients = getattr(exc, "recipients", None)
    if isinstance(recipients, dict):
        parts.extend(str(value) for value in recipients.values())
    return " ".join(parts).lower()


def classify_send_failure(exc: BaseException) -> tuple[str, str]:
    """Ngoại lệ thô của `smtplib` → ``(reason, câu cho người dùng)``.

    THỨ TỰ Ở ĐÂY LÀ BẮT BUỘC: `smtplib.SMTPException` **kế thừa `OSError`**, nên nếu xét
    nhánh mạng trước thì mọi lỗi SMTP — kể cả sai mật khẩu — đều bị gán nhầm thành "không
    kết nối được", và người dùng lại nhận đúng một lời khuyên vô nghĩa.  #Huynh
    """
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return "auth", _MSG_AUTH
    if isinstance(exc, smtplib.SMTPException):
        if any(marker in _server_reply_text(exc) for marker in _QUOTA_MARKERS):
            return "quota", _MSG_QUOTA
        if isinstance(exc, smtplib.SMTPConnectError | smtplib.SMTPServerDisconnected):
            return "connect", _MSG_CONNECT
        return "unknown", _MSG_UNKNOWN
    # TimeoutError phủ luôn `socket.timeout` (bí danh từ Python 3.10), ConnectionRefusedError
    # là con của OSError — đây là nhánh "chưa nói chuyện được với máy chủ thư".
    if isinstance(exc, TimeoutError | socket.gaierror | OSError):
        return "connect", _MSG_CONNECT
    return "unknown", _MSG_UNKNOWN


def _send_sync(
    *,
    to: str,
    subject: str,
    html: str,
    plain: str,
    from_name: str | None = None,
    reply_to: str | None = None,
    inline_images: dict[str, bytes] | None = None,
) -> None:
    # Có ảnh nhúng thì thư phải là `multipart/related` bọc ngoài `multipart/alternative`.
    #
    # Không thể nhúng ảnh bằng `data:image/png;base64` như trang web: Gmail CẮT BỎ ảnh dạng
    # đó. Cách duy nhất chạy được ở mọi trình đọc mail là đính kèm ảnh rồi trỏ vào bằng
    # `cid:`. Đổi lại, số tài khoản trong mã QR không phải đi qua máy chủ của bên thứ ba
    # nào — khác hẳn cách gọi dịch vụ sinh ảnh QR ngoài.  #Huynh
    if inline_images:
        msg = MIMEMultipart("related")
        body = MIMEMultipart("alternative")
        msg.attach(body)
    else:
        msg = MIMEMultipart("alternative")
        body = msg
    msg["Subject"] = subject
    # TÊN hiển thị đổi được, ĐỊA CHỈ thì không.
    #
    # Thư nhắc khách là freelancer nhắn cho khách của họ, nên khách phải thấy tên
    # freelancer. Nhưng KHÔNG thể đặt luôn địa chỉ của freelancer vào đây: hộp thư đi là
    # tài khoản của SoloDesk, khai địa chỉ người khác là mạo danh — Gmail ghi đè lại, còn
    # máy chủ của khách thì trượt SPF/DKIM và ném thư vào spam. Danh tính freelancer đi
    # bằng tên hiển thị + Reply-To, đó cũng là cách mọi SaaS gửi thay người dùng.  #Huynh
    sender_name = (from_name or "").strip() or settings.smtp_from_name
    # `formataddr(..., charset)` chứ KHÔNG phải f-string: tên freelancer có dấu tiếng Việt
    # nên header phải mã hoá — mà ghép chuỗi thì Python mã hoá luôn cả địa chỉ email
    # (`<a@b.com>` thành `=3Ca=40b=2Ecom=3E`), sai RFC 2047 và máy chủ thư có quyền từ
    # chối. `formataddr` chỉ mã hoá phần tên, để địa chỉ nguyên vẹn.  #Huynh
    msg["From"] = formataddr((sender_name, settings.smtp_from_email), charset="utf-8")
    msg["To"] = to
    if reply_to:
        # Khách bấm "Trả lời" là thư về thẳng freelancer, không vòng qua SoloDesk.
        msg["Reply-To"] = reply_to
    # Không khai thì Gmail đoán nhầm thư tiếng Việt là tiếng Anh và chìa ra banner
    # "Dịch sang Tiếng Việt" ngay trên đầu thư freelancer gửi khách — trông rất nghiệp dư.
    msg["Content-Language"] = "vi"

    body.attach(MIMEText(plain, "plain", "utf-8"))
    body.attach(MIMEText(html, "html", "utf-8"))

    for cid, data in (inline_images or {}).items():
        image = MIMEImage(data)
        # Dấu ngoặc nhọn theo RFC 2392; trong HTML thì trỏ bằng `cid:<tên>` không ngoặc.
        image.add_header("Content-ID", f"<{cid}>")
        image.add_header("Content-Disposition", "inline", filename=f"{cid}.png")
        msg.attach(image)

    smtp_cls = smtplib.SMTP_SSL if settings.smtp_tls else smtplib.SMTP
    # `timeout` PHẢI truyền: không có nó, một máy chủ thư im lặng treo lệnh này tới timeout
    # TCP của hệ điều hành (cỡ 2 phút) và giữ luôn một thread trong pool — trong khi trình
    # duyệt đã bỏ cuộc từ giây thứ 15 và người dùng chỉ thấy một câu lỗi vô nghĩa.
    # Xem `settings.smtp_timeout_seconds` để biết vì sao là 10 giây.  #Huynh
    with smtp_cls(
        settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout_seconds
    ) as server:
        if settings.smtp_starttls:
            server.ehlo()
            server.starttls()
            server.ehlo()
        if settings.smtp_user and settings.smtp_password:
            server.login(settings.smtp_user, settings.smtp_password)
        server.sendmail(settings.smtp_from_email, [to], msg.as_string())


async def send_email(
    *,
    to: str,
    subject: str,
    html: str,
    plain: str,
    from_name: str | None = None,
    reply_to: str | None = None,
    inline_images: dict[str, bytes] | None = None,
) -> None:
    """Gửi email (chạy SMTP trong thread pool để không chặn event loop).

    `from_name` / `reply_to` để gửi THAY MẶT một freelancer: khách thấy tên họ và trả lời
    về đúng hộp thư của họ. Bỏ trống thì thư mang danh SoloDesk (thư hệ thống như OTP).

    `inline_images` là `{tên: bytes PNG}` để nhúng bằng `<img src="cid:tên">` — dùng cho mã
    QR chuyển khoản trong thư nhắc thanh toán.

    Gửi hỏng thì ném `EmailDeliveryError` đã PHÂN LOẠI, không phải ngoại lệ thô của
    `smtplib`. Chỗ gọi (và qua đó là màn hình) nhờ vậy nói được *vì sao* hỏng thay vì chỉ
    "có lỗi xảy ra" — xem `classify_send_failure`.
    """
    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(
            None,
            partial(
                _send_sync,
                to=to,
                subject=subject,
                html=html,
                plain=plain,
                from_name=from_name,
                reply_to=reply_to,
                inline_images=inline_images,
            ),
        )
        logger.info("email.sent", to=to, subject=subject, reply_to=reply_to)
    except Exception as exc:
        reason, message = classify_send_failure(exc)
        # Log giữ NGUYÊN VĂN lỗi máy chủ thư trả về — đây là chỗ duy nhất còn đủ chi tiết
        # để truy nguyên. `reason` cho phép lọc log theo nhóm mà không phải đọc từng dòng.
        logger.error(
            "email.send_failed",
            to=to,
            subject=subject,
            reason=reason,
            error_type=type(exc).__name__,
            error=str(exc),
        )
        raise EmailDeliveryError(message, reason=reason) from exc
