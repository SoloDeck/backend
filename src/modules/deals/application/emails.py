"""Nội dung email thông báo cho freelancer khi có Deal mới từ form intake.

Tách builder ra hàm thuần (không I/O) để test được câu chữ + link mà không cần SMTP.
Đây là thư HỆ THỐNG gửi cho chính freelancer (không phải gửi thay họ cho khách), nên
không cần from_name/reply-to — giống email OTP.
"""

from dataclasses import dataclass
from html import escape


@dataclass(frozen=True)
class EmailContent:
    subject: str
    html: str
    plain: str


def build_new_deal_email(
    *,
    owner_name: str | None,
    client_name: str,
    project_name: str | None,
    deal_url: str,
) -> EmailContent:
    """Soạn email báo freelancer vừa nhận một Deal mới qua form intake."""
    greeting = (owner_name or "").strip() or "bạn"
    project = (project_name or "").strip() or "một dự án mới"

    subject = f"[SoloDesk] Deal mới từ {client_name}"

    plain = (
        f"Chào {greeting},\n\n"
        f'Bạn vừa nhận được một yêu cầu mới từ khách hàng "{client_name}" cho "{project}".\n\n'
        "SoloDesk đã tạo sẵn deal trong pipeline và đang chấm điểm AI cho lead này. "
        "Bạn vào xem sớm để không bỏ lỡ khách nhé:\n"
        f"{deal_url}\n\n"
        "— SoloDesk"
    )

    html = (
        '<div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;'
        'line-height:1.6;color:#111827;">'
        f"<p>Chào {escape(greeting)},</p>"
        f'<p>Bạn vừa nhận được một yêu cầu mới từ khách hàng '
        f"<strong>{escape(client_name)}</strong> cho <strong>{escape(project)}</strong>.</p>"
        "<p>SoloDesk đã tạo sẵn deal trong pipeline và đang chấm điểm AI cho lead này. "
        "Bạn vào xem sớm để không bỏ lỡ khách nhé.</p>"
        f'<p><a href="{escape(deal_url, quote=True)}" '
        'style="display:inline-block;background:#4f46e5;color:#ffffff;text-decoration:none;'
        'padding:10px 18px;border-radius:8px;font-weight:600;">Xem deal ngay</a></p>'
        '<p style="color:#6b7280;font-size:13px;">— SoloDesk</p>'
        "</div>"
    )

    return EmailContent(subject=subject, html=html, plain=plain)
