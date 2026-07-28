"""Async SMTP email sender.

Thin wrapper around Python's ``smtplib`` executed in a thread pool so it
does not block the event loop.
"""

import asyncio
import smtplib
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from functools import partial

import structlog

from src.config.settings import settings

logger = structlog.get_logger(__name__)


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
    with smtp_cls(settings.smtp_host, settings.smtp_port) as server:
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
        logger.error("email.send_failed", to=to, subject=subject, error=str(exc))
        raise
