"""Nội dung email gửi BÁO GIÁ cho khách của freelancer.

Hàm THUẦN (không I/O, không DB) — test được câu chữ mà không cần SMTP, cùng lối với
`invoices/application/emails.py` và `deals/application/emails.py`.

**Thư này chỉ là phong bì; tờ báo giá là file PDF đính kèm.** Khách không có tài khoản trong
hệ thống và web chưa có trang xem báo giá công khai, nên PDF là cách DUY NHẤT để khách đọc
được phạm vi, tiến độ và các đợt thanh toán. Thân thư vì vậy chỉ nêu đủ để khách biết đây là
gì và quyết định có mở file hay không: dự án nào, tổng bao nhiêu, hạn đến khi nào.  #Huynh
"""

from dataclasses import dataclass
from html import escape


@dataclass(frozen=True)
class EmailContent:
    subject: str
    html: str
    plain: str


def build_proposal_email(
    *,
    client_name: str,
    freelancer_name: str | None,
    project_name: str | None,
    total: str | None = None,
    valid_until: str | None = None,
    footer: str = "",
) -> EmailContent:
    """Soạn thư gửi khách kèm báo giá (file PDF đính kèm do chỗ gọi lo).

    `total` và `valid_until` là chuỗi ĐÃ ĐỊNH DẠNG sẵn từ chính tờ báo giá (`pricing_total`,
    `valid_until` của `ProposalDocument`) — lấy đúng thứ in trên PDF thay vì tự tính lại, để
    con số trong thân thư và con số trong file đính kèm không bao giờ lệch nhau. Trống thì bỏ
    dòng đó đi, đừng in "Tổng: " rồi để trắng.

    Tiêu đề **cố ý không gắn tiền tố `[SoloDesk]`**, giống thư hóa đơn và thư nhắc: đây là
    freelancer gửi cho khách của mình, gắn tên phần mềm vào là lộ ra rằng máy gửi.

    Mọi giá trị đều `escape()`: tên khách và tên dự án do người dùng gõ, chỉ một dấu `&`
    hay `<` là vỡ HTML của thư gửi khách.  #Huynh
    """
    sender = (freelancer_name or "").strip()
    project = (project_name or "").strip()
    total_text = (total or "").strip()
    valid_text = (valid_until or "").strip()

    subject = f"Báo giá dự án {project}" if project else "Báo giá dịch vụ"
    if sender:
        subject += f" từ {sender}"

    who = sender or "Chúng tôi"
    about = f'dự án "{project}"' if project else "dịch vụ"
    details: list[tuple[str, str]] = []
    if total_text:
        details.append(("Tổng giá trị", total_text))
    if valid_text:
        details.append(("Báo giá có hiệu lực đến", valid_text))

    # ---- bản chữ thuần ----------------------------------------------------------------
    plain_lines = [f"Chào {client_name},", "", f"{who} gửi bạn báo giá cho {about}.", ""]
    plain_lines += [f"- {label}: {value}" for label, value in details]
    if details:
        plain_lines.append("")
    plain_lines += [
        "Phạm vi công việc, tiến độ và các đợt thanh toán nằm trong file PDF đính kèm.",
        "Nếu bạn đồng ý hoặc cần điều chỉnh, cứ trả lời thẳng email này.",
    ]
    if footer:
        plain_lines += ["", footer]

    # ---- bản HTML ---------------------------------------------------------------------
    rows = "".join(
        "<tr>"
        f'<td style="padding:4px 16px 4px 0;color:#6b7280;">{escape(label)}</td>'
        f'<td style="padding:4px 0;font-weight:700;">{escape(value)}</td>'
        "</tr>"
        for label, value in details
    )
    details_block = (
        f'<table style="border-collapse:collapse;font-size:14px;margin:4px 0 12px;">{rows}</table>'
        if rows
        else ""
    )
    footer_block = (
        f'<p style="color:#6b7280;font-size:13px;white-space:pre-line;">{escape(footer)}</p>'
        if footer
        else ""
    )
    html = (
        '<div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;'
        'line-height:1.6;color:#111827;">'
        f"<p>Chào {escape(client_name)},</p>"
        f"<p><strong>{escape(who)}</strong> gửi bạn báo giá cho {escape(about)}.</p>"
        f"{details_block}"
        "<p>Phạm vi công việc, tiến độ và các đợt thanh toán nằm trong file PDF đính kèm. "
        "Nếu bạn đồng ý hoặc cần điều chỉnh, cứ trả lời thẳng email này.</p>"
        f"{footer_block}"
        "</div>"
    )

    return EmailContent(subject=subject, html=html, plain="\n".join(plain_lines))
