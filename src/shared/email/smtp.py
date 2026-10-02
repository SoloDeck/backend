"""Async SMTP email sender.

Thin wrapper around Python's ``smtplib`` executed in a thread pool so it
does not block the event loop.
"""

import asyncio
import re
import smtplib
import socket
from email import encoders
from email.mime.base import MIMEBase
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
# Thử lại cũng vô ích — phải sửa địa chỉ người nhận. Tách riêng khỏi `unknown` để người dùng biết
# việc cần làm là kiểm tra email khách, không phải ngồi đợi.  #Huynh
_MSG_RECIPIENT = (
    "Máy chủ thư không nhận địa chỉ email của người nhận (có thể gõ sai hoặc không tồn tại). "
    "Hãy kiểm tra lại email rồi gửi lại."
)
# Hộp thư của KHÁCH đầy. Cũng là chuyện của người nhận (không phải của hệ thống), nhưng việc cần
# làm khác `_MSG_RECIPIENT`: địa chỉ đúng, chỉ là họ phải dọn hộp thư hoặc đưa địa chỉ khác.
_MSG_RECIPIENT_FULL = (
    "Hộp thư của người nhận đang đầy hoặc không nhận thêm thư lúc này. "
    "Hãy báo khách dọn hộp thư hoặc dùng địa chỉ email khác, rồi gửi lại."
)

# Hạn mức của HỆ THỐNG — hộp thư SoloDesk dùng để gửi. Gmail báo bằng `550 5.4.5 Daily user
# sending limit exceeded`, nhưng gói nó vào lớp ngoại lệ nào thì tuỳ bước gửi hỏng (DATA / RCPT /
# MAIL FROM). Nên nhận diện bằng NỘI DUNG câu trả lời của máy chủ, không bằng lớp ngoại lệ.
#
# Chỉ gồm những cụm NÓI RÕ là chuyện của người GỬI ("sending", "rate"), tuyệt đối không có từ
# "quota" trơ trọi: hộp thư của người NHẬN đầy cũng báo "over quota" (`552 5.2.2 ... over quota`),
# và gán nó cho hệ thống là bảo freelancer "thử lại sau vài giờ" trong khi khách phải dọn hộp thư.
_SYSTEM_QUOTA_MARKERS = (
    "daily user sending",
    "sending limit",
    "sending quota",
    "message quota",
    "rate limit",
    "too many messages",
)
# Mã trạng thái nâng cao RFC 3463. Có lookbehind/lookahead để `185.4.5.6` (một địa chỉ IP trong
# câu từ chối) không bị nhận nhầm thành mã `5.4.5`.
_SYSTEM_QUOTA_CODE = re.compile(r"(?<![\w.])5\.4\.5(?!\d)")

# Hộp thư của NGƯỜI NHẬN đầy. `5.2.2` / `4.2.2` là mã "mailbox full" chuẩn.
_MAILBOX_FULL_MARKERS = ("quota", "mailbox full", "mailbox is full")
_MAILBOX_FULL_CODE = re.compile(r"(?<![\w.])[45]\.2\.2(?!\d)")


def _server_reply_text(exc: BaseException) -> str:
    """Gom mọi mẩu văn bản máy chủ thư trả về trong một ngoại lệ smtplib."""
    # SMTPRecipientsRefused gói lý do theo từng người nhận, không có `smtp_error`. CHỈ lấy phần
    # lý do máy chủ trả về, không lấy địa chỉ (khoá của dict): địa chỉ là chữ do khách đặt, một
    # hộp thư tên `quota@...` không được phép làm lệch việc phân loại.
    recipients = getattr(exc, "recipients", None)
    if isinstance(recipients, dict):
        return " ".join(str(value) for value in recipients.values()).lower()
    parts = [str(exc)]
    raw = getattr(exc, "smtp_error", None)
    if isinstance(raw, bytes | bytearray):
        parts.append(bytes(raw).decode("utf-8", "replace"))
    elif raw:
        parts.append(str(raw))
    return " ".join(parts).lower()


def _is_system_quota(reply: str) -> bool:
    """Câu trả lời này nói hệ thống (người GỬI) đã chạm hạn mức gửi?"""
    return bool(_SYSTEM_QUOTA_CODE.search(reply)) or any(
        marker in reply for marker in _SYSTEM_QUOTA_MARKERS
    )


def _is_mailbox_full(reply: str) -> bool:
    """Câu trả lời này nói hộp thư của người NHẬN đầy / hết dung lượng?"""
    return bool(_MAILBOX_FULL_CODE.search(reply)) or any(
        marker in reply for marker in _MAILBOX_FULL_MARKERS
    )


def _is_recipient_text(exc: UnicodeEncodeError, recipient: str | None) -> bool:
    """Ký tự `smtplib` không mã hoá được có nằm TRONG địa chỉ người nhận không?

    `exc.object` là cả chuỗi đang được mã hoá — nguyên một lệnh (`rcpt TO:<khách@...>`) chứ không
    riêng địa chỉ — còn `exc.start:exc.end` là chỗ ký tự hỏng. Lỗi chỉ thuộc về người nhận khi
    ký tự hỏng nằm trong đúng địa chỉ của họ.  #Huynh
    """
    if not recipient:
        return False
    text = exc.object
    offset = text.find(recipient)
    while offset != -1:
        if offset <= exc.start and exc.end <= offset + len(recipient):
            return True
        offset = text.find(recipient, offset + 1)
    return False


def classify_send_failure(exc: BaseException, *, recipient: str | None = None) -> tuple[str, str]:
    """Ngoại lệ thô của `smtplib` → ``(reason, câu cho người dùng)``.

    `recipient` là địa chỉ người nhận của lượt gửi này. Chỉ cần để phân biệt `UnicodeEncodeError`
    của người nhận với của hệ thống; không truyền thì lỗi đó được xếp `unknown`, không đoán.

    THỨ TỰ Ở ĐÂY LÀ BẮT BUỘC: `smtplib.SMTPException` **kế thừa `OSError`**, nên nếu xét
    nhánh mạng trước thì mọi lỗi SMTP — kể cả sai mật khẩu — đều bị gán nhầm thành "không
    kết nối được", và người dùng lại nhận đúng một lời khuyên vô nghĩa.  #Huynh
    """
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return "auth", _MSG_AUTH
    if isinstance(exc, smtplib.SMTPException):
        reply = _server_reply_text(exc)
        # Hạn mức của HỆ THỐNG xét TRƯỚC nhánh người nhận: Gmail gói lỗi hết hạn mức gửi vào đúng
        # lớp `SMTPRecipientsRefused`, nhưng đó vẫn là chuyện của hộp thư hệ thống.
        if _is_system_quota(reply):
            return "quota", _MSG_QUOTA
        # Máy chủ từ chối người nhận. Hộp thư của khách đầy cũng đi đường này (`552 5.2.2 ... over
        # quota`): địa chỉ đúng nhưng việc cần làm khác "gõ sai", nên có câu riêng.
        if isinstance(exc, smtplib.SMTPRecipientsRefused):
            if _is_mailbox_full(reply):
                return "recipient", _MSG_RECIPIENT_FULL
            return "recipient", _MSG_RECIPIENT
        # Các lớp còn lại (lỗi MAIL FROM / DATA...): "quota" ở đây vẫn là hạn mức của hệ thống.
        if "quota" in reply:
            return "quota", _MSG_QUOTA
        if isinstance(exc, smtplib.SMTPConnectError | smtplib.SMTPServerDisconnected):
            return "connect", _MSG_CONNECT
        return "unknown", _MSG_UNKNOWN
    # `smtplib` mã hoá MỌI lệnh gửi đi bằng ASCII: EHLO (tên máy), AUTH (tài khoản + mật khẩu),
    # MAIL FROM (địa chỉ gửi), RCPT TO (địa chỉ nhận). Chữ có dấu ở bất kỳ chỗ nào đều nổ
    # `UnicodeEncodeError`, nên lỗi này chỉ là lỗi của NGƯỜI NHẬN khi ký tự hỏng nằm trong địa chỉ
    # của họ (`khách@...`). Mật khẩu ứng dụng dán từ Google hay chứa dấu cách không ngắt (NBSP) —
    # đó là lỗi cấu hình phía ta, bảo freelancer "kiểm tra email khách" là chỉ sai đường.
    if isinstance(exc, UnicodeEncodeError):
        if _is_recipient_text(exc, recipient):
            return "recipient", _MSG_RECIPIENT
        return "unknown", _MSG_UNKNOWN
    # TimeoutError phủ luôn `socket.timeout` (bí danh từ Python 3.10), ConnectionRefusedError
    # là con của OSError — đây là nhánh "chưa nói chuyện được với máy chủ thư".
    if isinstance(exc, TimeoutError | socket.gaierror | OSError):
        return "connect", _MSG_CONNECT
    return "unknown", _MSG_UNKNOWN


def _one_line(value: str | None) -> str:
    r"""Gộp CR/LF/Tab thành một dấu cách — header thư là MỘT dòng.

    Thư viện `email` đã chặn tiêm header thật (ném `HeaderParseError`), nhưng tên hiển thị và
    tiêu đề vẫn lọt qua với ký tự xuống dòng nằm bên trong: tên freelancer `Evil\r\nBcc: x`
    thành một tên người gửi có CRLF, còn parser chuẩn thì từ chối đọc header From. Tên và tiêu
    đề do người dùng gõ nên phải làm sạch ở đây, đừng trông vào chỗ gõ vào.  #Huynh
    """
    if not value:
        return ""
    return " ".join(value.replace("\r", " ").replace("\n", " ").replace("\t", " ").split())


def _attachment_part(filename: str, data: bytes, mime_type: str) -> MIMEBase:
    """Dựng một phần thư là FILE ĐÍNH KÈM (khác ảnh nhúng: phần này hiện thành tệp để tải).

    Tên file có dấu tiếng Việt thì khai theo RFC 2231 (`filename*=utf-8''...`) — để nguyên
    chữ có dấu trong header là nhiều trình đọc mail đọc ra tên rác. Tên thuần ASCII thì để
    nguyên dạng thường cho mọi nơi đọc được.  #Huynh
    """
    maintype, _, subtype = mime_type.partition("/")
    part = MIMEBase(maintype or "application", subtype or "octet-stream")
    part.set_payload(data)
    encoders.encode_base64(part)
    name = filename if filename.isascii() else ("utf-8", "", filename)
    part.add_header("Content-Disposition", "attachment", filename=name)
    return part


def _send_sync(
    *,
    to: str,
    subject: str,
    html: str,
    plain: str,
    from_name: str | None = None,
    reply_to: str | None = None,
    inline_images: dict[str, bytes] | None = None,
    attachments: list[tuple[str, bytes, str]] | None = None,
) -> None:
    # Có ảnh nhúng thì thư phải là `multipart/related` bọc ngoài `multipart/alternative`.
    #
    # Không thể nhúng ảnh bằng `data:image/png;base64` như trang web: Gmail CẮT BỎ ảnh dạng
    # đó. Cách duy nhất chạy được ở mọi trình đọc mail là đính kèm ảnh rồi trỏ vào bằng
    # `cid:`. Đổi lại, số tài khoản trong mã QR không phải đi qua máy chủ của bên thứ ba
    # nào — khác hẳn cách gọi dịch vụ sinh ảnh QR ngoài.  #Huynh
    if inline_images:
        content = MIMEMultipart("related")
        body = MIMEMultipart("alternative")
        content.attach(body)
    else:
        content = MIMEMultipart("alternative")
        body = content
    # Có file đính kèm (PDF báo giá, hợp đồng) thì cả khối nội dung ở trên phải nằm trong một
    # `multipart/mixed` — đó là vỏ chuẩn để trình đọc mail hiện thân thư kèm danh sách tệp.
    # Header (Subject/From/To...) phải đặt lên VỎ NGOÀI CÙNG, nên `msg` là vỏ đó.  #Huynh
    if attachments:
        msg = MIMEMultipart("mixed")
        msg.attach(content)
    else:
        msg = content
    msg["Subject"] = _one_line(subject)
    # TÊN hiển thị đổi được, ĐỊA CHỈ thì không.
    #
    # Thư nhắc khách là freelancer nhắn cho khách của họ, nên khách phải thấy tên
    # freelancer. Nhưng KHÔNG thể đặt luôn địa chỉ của freelancer vào đây: hộp thư đi là
    # tài khoản của SoloDesk, khai địa chỉ người khác là mạo danh — Gmail ghi đè lại, còn
    # máy chủ của khách thì trượt SPF/DKIM và ném thư vào spam. Danh tính freelancer đi
    # bằng tên hiển thị + Reply-To, đó cũng là cách mọi SaaS gửi thay người dùng.  #Huynh
    sender_name = _one_line(from_name) or settings.smtp_from_name
    # `formataddr(..., charset)` chứ KHÔNG phải f-string: tên freelancer có dấu tiếng Việt
    # nên header phải mã hoá — mà ghép chuỗi thì Python mã hoá luôn cả địa chỉ email
    # (`<a@b.com>` thành `=3Ca=40b=2Ecom=3E`), sai RFC 2047 và máy chủ thư có quyền từ
    # chối. `formataddr` chỉ mã hoá phần tên, để địa chỉ nguyên vẹn.  #Huynh
    msg["From"] = formataddr((sender_name, settings.smtp_from_email), charset="utf-8")
    msg["To"] = to
    if reply_to:
        # Khách bấm "Trả lời" là thư về thẳng freelancer, không vòng qua SoloDesk.
        msg["Reply-To"] = _one_line(reply_to)
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
        content.attach(image)

    for filename, data, mime_type in attachments or []:
        msg.attach(_attachment_part(filename, data, mime_type))

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
    attachments: list[tuple[str, bytes, str]] | None = None,
) -> None:
    """Gửi email (chạy SMTP trong thread pool để không chặn event loop).

    `from_name` / `reply_to` để gửi THAY MẶT một freelancer: khách thấy tên họ và trả lời
    về đúng hộp thư của họ. Bỏ trống thì thư mang danh SoloDesk (thư hệ thống như OTP).

    `inline_images` là `{tên: bytes PNG}` để nhúng bằng `<img src="cid:tên">` — dùng cho mã
    QR chuyển khoản trong thư nhắc thanh toán.

    `attachments` là danh sách `(tên_file, bytes, mime_type)` — file khách tải về được, ví dụ
    PDF báo giá hoặc hợp đồng gửi kèm thư.

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
                attachments=attachments,
            ),
        )
        logger.info("email.sent", to=to, subject=subject, reply_to=reply_to)
    except Exception as exc:
        reason, message = classify_send_failure(exc, recipient=to)
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
