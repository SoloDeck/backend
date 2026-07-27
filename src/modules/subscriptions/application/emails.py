"""Email vòng đời gói dịch vụ: sắp hết quota AI, sắp hết kỳ, và đã hạ về Free.

Toàn bộ là thư HỆ THỐNG gửi cho chính freelancer (không gửi thay họ cho khách), nên không
cần from_name/reply-to — giống email OTP. Builder tách thành hàm thuần để test câu chữ mà
không cần SMTP.
"""

from dataclasses import dataclass
from datetime import datetime
from html import escape


@dataclass(frozen=True)
class EmailContent:
    subject: str
    html: str
    plain: str


def _vn_date(value: datetime) -> str:
    return f"{value.day:02d}/{value.month:02d}/{value.year}"


def _wrap_html(body: str, cta_url: str | None = None) -> str:
    cta = (
        (
            f'<p><a href="{escape(cta_url, quote=True)}" '
            'style="display:inline-block;background:#4f46e5;color:#ffffff;text-decoration:none;'
            'padding:10px 18px;border-radius:8px;font-weight:600;">Xem gói dịch vụ</a></p>'
        )
        if cta_url
        else ""
    )
    return (
        '<div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;'
        f'line-height:1.6;color:#111827;">{body}{cta}'
        '<p style="color:#6b7280;font-size:13px;">— SoloDesk</p></div>'
    )


def build_quota_warning_email(
    *,
    owner_name: str | None,
    used: int,
    limit: int,
    period_end: datetime,
    plan_url: str | None = None,
) -> EmailContent:
    """Sắp hết hạn mức AI trong kỳ (chưa tới ngày hết hạn gói)."""
    greeting = (owner_name or "").strip() or "bạn"
    remaining = max(0, limit - used)
    subject = "[SoloDesk] Bạn sắp hết lượt AI trong kỳ này"

    plain = (
        f"Chào {greeting},\n\n"
        f"Bạn đã dùng {used}/{limit} lượt AI trong kỳ hiện tại, chỉ còn {remaining} lượt. "
        f"Hạn mức sẽ làm mới vào ngày {_vn_date(period_end)}.\n\n"
        "Nếu cần thêm lượt trước thời điểm đó, bạn có thể nâng cấp gói dịch vụ.\n\n"
        "— SoloDesk"
    )
    html = _wrap_html(
        f"<p>Chào {escape(greeting)},</p>"
        f"<p>Bạn đã dùng <strong>{used}/{limit}</strong> lượt AI trong kỳ hiện tại, "
        f"chỉ còn <strong>{remaining}</strong> lượt. Hạn mức sẽ làm mới vào ngày "
        f"<strong>{_vn_date(period_end)}</strong>.</p>"
        "<p>Nếu cần thêm lượt trước thời điểm đó, bạn có thể nâng cấp gói dịch vụ.</p>",
        plan_url,
    )
    return EmailContent(subject=subject, html=html, plain=plain)


def build_expiry_warning_email(
    *,
    owner_name: str | None,
    plan_name: str,
    period_end: datetime,
    days_left: int,
    plan_url: str | None = None,
) -> EmailContent:
    """Gói trả phí sắp tới ngày hết hạn (báo trước)."""
    greeting = (owner_name or "").strip() or "bạn"
    subject = f"[SoloDesk] Gói {plan_name} của bạn sắp hết hạn"

    plain = (
        f"Chào {greeting},\n\n"
        f"Gói {plan_name} của bạn sẽ hết hạn vào ngày {_vn_date(period_end)} "
        f"(còn {days_left} ngày). Khi hết hạn, tài khoản sẽ tự chuyển về gói Miễn phí.\n\n"
        "Bạn gia hạn để không gián đoạn các tính năng AI nhé.\n\n"
        "— SoloDesk"
    )
    html = _wrap_html(
        f"<p>Chào {escape(greeting)},</p>"
        f"<p>Gói <strong>{escape(plan_name)}</strong> của bạn sẽ hết hạn vào ngày "
        f"<strong>{_vn_date(period_end)}</strong> (còn <strong>{days_left}</strong> ngày). "
        "Khi hết hạn, tài khoản sẽ tự chuyển về gói Miễn phí.</p>"
        "<p>Bạn gia hạn để không gián đoạn các tính năng AI nhé.</p>",
        plan_url,
    )
    return EmailContent(subject=subject, html=html, plain=plain)
