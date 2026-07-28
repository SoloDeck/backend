"""Nội dung email thông báo cho freelancer khi có Deal mới từ form intake.

Tách builder ra hàm thuần (không I/O) để test được câu chữ + link mà không cần SMTP.
Đây là thư HỆ THỐNG gửi cho chính freelancer (không phải gửi thay họ cho khách), nên
không cần from_name/reply-to — giống email OTP.
"""

from dataclasses import dataclass
from html import escape

# Trích yêu cầu của khách ở mức đọc-lướt-hiểu-ngay. Dài hơn thì email thành bản sao của
# trang chi tiết deal, mà việc của nó chỉ là đủ thông tin để quyết "có gọi lại ngay không".
INQUIRY_EXCERPT_LIMIT = 300


@dataclass(frozen=True)
class EmailContent:
    subject: str
    html: str
    plain: str


def _excerpt(text: str | None, limit: int = INQUIRY_EXCERPT_LIMIT) -> str:
    value = (text or "").strip()
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "…"


def build_new_deal_email(
    *,
    owner_name: str | None,
    client_name: str,
    project_name: str | None,
    deal_url: str,
    client_email: str | None = None,
    client_phone: str | None = None,
    budget: str | None = None,
    timeline: str | None = None,
    inquiry_text: str | None = None,
    attachment_count: int = 0,
) -> EmailContent:
    """Soạn email báo freelancer vừa nhận một Deal mới qua form intake.

    Bản đầu chỉ có tên khách + tên dự án + một nút bấm — đọc xong vẫn phải mở app lên mới
    biết khách muốn gì, ngân sách bao nhiêu, có gửi tệp không. Nhận yêu cầu lúc đang chạy
    ngoài đường mà phải mở laptop mới biết có đáng gọi lại hay không thì email coi như vô
    dụng. Giờ thư tự nó đủ để quyết.

    MỌI giá trị dưới đây do người lạ trên internet nhập vào form công khai, nên phải
    `escape()` hết trước khi ghép vào HTML.  #Huynh
    """
    greeting = (owner_name or "").strip() or "bạn"
    project = (project_name or "").strip() or "một dự án mới"
    excerpt = _excerpt(inquiry_text)

    subject = f"[SoloDesk] Deal mới: {project} — {client_name}"

    # (nhãn, giá trị) — bỏ qua dòng khách không điền, đừng bày ra một bảng đầy dấu gạch.
    rows: list[tuple[str, str]] = [("Khách hàng", client_name)]
    if client_email:
        rows.append(("Email", client_email))
    if client_phone:
        rows.append(("Điện thoại", client_phone))
    if budget:
        rows.append(("Ngân sách dự kiến", budget))
    if timeline:
        rows.append(("Thời gian mong muốn", timeline))
    if attachment_count > 0:
        rows.append(("Tệp đính kèm", f"{attachment_count} tệp"))

    plain_rows = "\n".join(f"- {label}: {value}" for label, value in rows)
    plain = (
        f"Chào {greeting},\n\n"
        f'Bạn vừa nhận được một yêu cầu mới cho "{project}".\n\n'
        f"{plain_rows}\n"
    )
    if excerpt:
        plain += f"\nKhách viết:\n{excerpt}\n"
    plain += (
        "\nSoloDesk đã tạo sẵn deal trong pipeline và đang chấm điểm AI cho lead này. "
        "Bạn vào xem sớm để không bỏ lỡ khách nhé:\n"
        f"{deal_url}\n\n"
        "— SoloDesk"
    )

    html_rows = "".join(
        "<tr>"
        f'<td style="padding:6px 12px 6px 0;color:#6b7280;white-space:nowrap;">'
        f"{escape(label)}</td>"
        f'<td style="padding:6px 0;font-weight:600;">{escape(value)}</td>'
        "</tr>"
        for label, value in rows
    )

    excerpt_block = (
        (
            '<div style="margin:16px 0;padding:12px 14px;background:#f9fafb;'
            'border-left:3px solid #4f46e5;border-radius:4px;">'
            '<div style="font-size:12px;color:#6b7280;margin-bottom:4px;">Khách viết</div>'
            f'<div style="white-space:pre-wrap;">{escape(excerpt)}</div>'
            "</div>"
        )
        if excerpt
        else ""
    )

    html = (
        '<div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;'
        'line-height:1.6;color:#111827;">'
        f"<p>Chào {escape(greeting)},</p>"
        f"<p>Bạn vừa nhận được một yêu cầu mới cho <strong>{escape(project)}</strong>.</p>"
        '<table style="border-collapse:collapse;font-size:14px;margin:12px 0;">'
        f"{html_rows}"
        "</table>"
        f"{excerpt_block}"
        "<p>SoloDesk đã tạo sẵn deal trong pipeline và đang chấm điểm AI cho lead này. "
        "Bạn vào xem sớm để không bỏ lỡ khách nhé.</p>"
        f'<p><a href="{escape(deal_url, quote=True)}" '
        'style="display:inline-block;background:#4f46e5;color:#ffffff;text-decoration:none;'
        'padding:10px 18px;border-radius:8px;font-weight:600;">Xem deal ngay</a></p>'
        '<p style="color:#6b7280;font-size:13px;">— SoloDesk</p>'
        "</div>"
    )

    return EmailContent(subject=subject, html=html, plain=plain)
