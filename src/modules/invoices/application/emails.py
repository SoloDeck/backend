"""Nội dung email hóa đơn gửi cho KHÁCH của freelancer.

Hàm THUẦN (không I/O, không DB) — test được câu chữ và số tiền mà không cần SMTP, cùng lối
với `deals/application/emails.py` và `reminders/application/payment_block.py`.

**Thư này phải TỰ ĐỦ.** Khách không có tài khoản trong hệ thống và sẽ không đăng nhập vào
đâu cả, nên mọi thứ họ cần để trả tiền — số tiền, hạn, nội dung chuyển khoản, số tài khoản —
phải nằm ngay trong thân thư. Bắt khách bấm ra một trang nữa chỉ để biết phải chuyển bao
nhiêu là thêm một bước có thể rụng.

Khối thanh toán và khối ảnh được TRUYỀN VÀO chứ không dựng ở đây: chúng cần đọc kho lưu trữ
và hồ sơ freelancer, mà file này thì phải giữ thuần.  #Huynh
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from html import escape


@dataclass(frozen=True)
class EmailContent:
    subject: str
    html: str
    plain: str


def format_vnd(amount: Decimal | int) -> str:
    """`1500000` → `"1.500.000 ₫"`. Dấu chấm phân cách nghìn theo lối Việt Nam."""
    return f"{int(amount):,} ₫".replace(",", ".")


def _fmt_date(value: date) -> str:
    return value.strftime("%d/%m/%Y")


def build_invoice_email(
    *,
    client_name: str,
    freelancer_name: str | None,
    invoice_number: str,
    line_items: list[tuple[str, Decimal]],
    total: Decimal,
    amount_due: Decimal,
    issue_date: date,
    due_date: date,
    notes: str | None = None,
    payment_html: str = "",
    payment_plain: str = "",
    images_html: str = "",
    footer: str = "",
) -> EmailContent:
    """Soạn thư gửi khách kèm chi tiết hóa đơn.

    `amount_due` tách khỏi `total` vì hóa đơn có thể đã thu một phần — gửi lại mà vẫn ghi
    nguyên tổng là đòi khách trả hai lần phần họ đã chuyển.

    Tiêu đề **cố ý không gắn tiền tố `[SoloDesk]`**, giống `reminders.build_subject`: đây là
    freelancer gửi cho khách của mình, không phải hệ thống thông báo. Gắn tên phần mềm vào
    là lộ ra rằng máy gửi.

    Mọi giá trị đều `escape()`: tên khách, nhãn hạng mục và ghi chú đều do người dùng gõ, chỉ
    một dấu `&` hay `<` là vỡ HTML của thư gửi khách.  #Huynh
    """
    sender = (freelancer_name or "").strip()
    subject = f"Hóa đơn {invoice_number}" + (f" từ {sender}" if sender else "")

    partially_paid = amount_due != total
    due_label = "Còn phải thanh toán" if partially_paid else "Tổng cộng"

    # ---- bản chữ thuần ----------------------------------------------------------------
    plain_lines = [
        f"Chào {client_name},",
        "",
        (
            f"{sender} gửi bạn hóa đơn {invoice_number}."
            if sender
            else f"Đây là hóa đơn {invoice_number}."
        ),
        "",
        f"Ngày lập: {_fmt_date(issue_date)}",
        f"Hạn thanh toán: {_fmt_date(due_date)}",
        "",
    ]
    plain_lines += [f"- {label}: {format_vnd(amount)}" for label, amount in line_items]
    if partially_paid:
        plain_lines.append(f"Tổng hóa đơn: {format_vnd(total)}")
    plain_lines.append(f"{due_label}: {format_vnd(amount_due)}")
    if notes:
        plain_lines += ["", f"Ghi chú: {notes}"]
    if payment_plain:
        plain_lines += ["", payment_plain]
    if footer:
        plain_lines += ["", footer]

    # ---- bản HTML ---------------------------------------------------------------------
    rows = "".join(
        "<tr>"
        f'<td style="padding:6px 12px 6px 0;">{escape(label)}</td>'
        f'<td style="padding:6px 0;text-align:right;white-space:nowrap;">'
        f"{escape(format_vnd(amount))}</td>"
        "</tr>"
        for label, amount in line_items
    )
    if partially_paid:
        rows += (
            "<tr>"
            '<td style="padding:6px 12px 6px 0;color:#6b7280;">Tổng hóa đơn</td>'
            '<td style="padding:6px 0;text-align:right;color:#6b7280;white-space:nowrap;">'
            f"{escape(format_vnd(total))}</td>"
            "</tr>"
        )
    rows += (
        '<tr><td colspan="2" style="border-top:1px solid #e5e7eb;padding:0;"></td></tr>'
        "<tr>"
        f'<td style="padding:10px 12px 0 0;font-weight:700;">{escape(due_label)}</td>'
        '<td style="padding:10px 0 0;text-align:right;font-weight:700;font-size:17px;'
        f'white-space:nowrap;">{escape(format_vnd(amount_due))}</td>'
        "</tr>"
    )

    intro = (
        f"<strong>{escape(sender)}</strong> gửi bạn hóa đơn "
        f"<strong>{escape(invoice_number)}</strong>."
        if sender
        else f"Đây là hóa đơn <strong>{escape(invoice_number)}</strong>."
    )

    notes_block = (
        (
            '<div style="margin:16px 0;padding:12px 14px;background:#f9fafb;'
            'border-left:3px solid #4f46e5;border-radius:4px;white-space:pre-wrap;">'
            f"{escape(notes)}</div>"
        )
        if notes
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
        f"<p>{intro}</p>"
        '<table style="border-collapse:collapse;font-size:14px;margin:4px 0 12px;'
        'min-width:320px;">'
        f"{rows}"
        "</table>"
        f'<p style="font-size:14px;color:#6b7280;">Ngày lập {escape(_fmt_date(issue_date))}'
        f' · Hạn thanh toán <strong style="color:#111827;">{escape(_fmt_date(due_date))}'
        "</strong></p>"
        f"{notes_block}"
        f"{payment_html}"
        f"{images_html}"
        f"{footer_block}"
        "</div>"
    )

    return EmailContent(subject=subject, html=html, plain="\n".join(plain_lines))
