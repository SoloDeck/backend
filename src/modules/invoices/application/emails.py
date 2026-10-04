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

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from html import escape

from src.modules.invoices.domain.typed_amounts import mismatched_amounts
from src.shared.exceptions.domain import BusinessRuleError

# Chỗ giữ chỗ `{{tong_tien}}` trong lời nhắn: server điền số thật (`amount_due`) lúc dựng thư.
#
# Web KHÔNG còn sinh chỗ giữ chỗ này (lời nhắn mẫu ghi số thật, tự đổi theo ô số tiền) — nhưng một
# số bản nháp tạo trong thời gian đó còn mang nó, và gửi nguyên chữ "{{tong_tien}}" tới khách là
# lỗi. Nên vẫn điền, như một lớp đỡ.  #Huynh
AMOUNT_PLACEHOLDER = "{{tong_tien}}"
_AMOUNT_PLACEHOLDER_RE = re.compile(r"\{\{\s*tong_tien\s*\}\}", re.IGNORECASE)


@dataclass(frozen=True)
class EmailContent:
    subject: str
    html: str
    plain: str


def format_vnd(amount: Decimal | int) -> str:
    """`1500000` → `"1.500.000 ₫"`. Dấu chấm phân cách nghìn theo lối Việt Nam."""
    return f"{int(amount):,} ₫".replace(",", ".")


def fill_amount_placeholder(text: str | None, amount: Decimal | int) -> str | None:
    """Thay mọi `{{tong_tien}}` trong `text` bằng số tiền định dạng kiểu Việt (`1.500.000 ₫`).

    Chịu được khoảng trắng và hoa/thường (`{{ TONG_TIEN }}`) vì chữ này do người dùng gõ
    trong ô văn bản tự do. Không có chỗ giữ chỗ thì trả nguyên văn.
    """
    if not text:
        return text
    return _AMOUNT_PLACEHOLDER_RE.sub(lambda _: format_vnd(amount), text)


# Dòng đầu của `notes` do web lưu là TÊN hóa đơn: `Hóa đơn: <tên>`, một dòng trống, rồi mới tới lời
# nhắn. Hóa đơn không có cột riêng cho tên nên web gửi lên ké trong `notes`; web nhận diện lại bằng
# đúng biểu thức này (`extractInvoiceTitle` ở `web/src/features/deals/invoiceComposer.ts`) — hai
# bên phải cùng một cách nhận diện, lệch là dòng tên lọt ra thư hoặc lời nhắn bị cắt mất.  #Huynh
_INVOICE_TITLE_LINE_RE = re.compile(r"^Hóa đơn:\s*(.+)$", re.IGNORECASE)


def strip_invoice_title_line(notes: str | None) -> str | None:
    """Bỏ dòng tên nội bộ `Hóa đơn: <tên>` ở đầu ghi chú, giữ nguyên lời nhắn bên dưới.

    Cửa sổ soạn hóa đơn hiện tên ở ô "Tên hóa đơn" riêng và lời nhắn ở ô bên dưới; dòng này chỉ là
    chỗ web cất tên. Đưa nguyên `notes` vào thư thì khách đọc thấy "Ghi chú: Hóa đơn: Thanh toán
    đợt 1" ngay trên lời chào — một dòng của phần mềm lọt ra ngoài.

    Chỉ xét DÒNG ĐẦU: chữ "Hóa đơn:" nằm ở giữa lời nhắn là lời của freelancer, giữ nguyên. Không có
    dòng tên (hóa đơn tạo bằng cách khác) thì trả lại đúng văn bản gốc. Ghi chú chỉ có mỗi dòng tên
    thì kết quả rỗng, và thư không có khối Ghi chú.
    """
    if not notes:
        return notes
    first_line, _, rest = notes.strip().partition("\n")
    if not _INVOICE_TITLE_LINE_RE.match(first_line.rstrip("\r")):
        return notes
    return rest.lstrip()


def _fmt_date(value: date) -> str:
    return value.strftime("%d/%m/%Y")


def build_invoice_footer(
    sender_name: str | None,
    sender_email: str | None,
    project_name: str | None,
) -> str:
    """Chân thư hóa đơn: AI gửi, VỀ DỰ ÁN NÀO, và khách KHÔNG cần trả lời.

    Riêng cho hóa đơn, không dùng chung `reminders.build_footer`, vì hai chỗ khác nhau:

    - chân chung ghi "Về dự án: <nhãn>" mà chỗ gọi từng truyền MÃ HÓA ĐƠN vào ("Về dự án: Hóa đơn
      INV-…") — khách đọc ra một cái tên dự án không có thật. Ở đây là tên dự án thật;
    - chân chung mời khách "trả lời email này, thư về thẳng hộp thư freelancer". Hóa đơn là thư
      thông báo: khách trả tiền bằng chuyển khoản theo thông tin ghi sẵn, không cần hồi âm. (Hợp
      đồng thì khác — thư hợp đồng chủ động xin khách trả lời kèm bản đã ký — nên chân chung giữ
      nguyên cho các thư đó.)  #Huynh
    """
    name = (sender_name or "").strip()
    if not name:
        return ""

    email = (sender_email or "").strip()
    who = f"{name} ({email})" if email else name
    lines = [f"Email này được gửi từ {who} qua SoloDesk."]
    project = (project_name or "").strip()
    if project:
        lines.append(f"Về dự án: {project}.")
    lines.append("Bạn không cần trả lời email này.")
    return "\n".join(lines)


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
    project_name: str | None = None,
    notes: str | None = None,
    payment_html: str = "",
    payment_plain: str = "",
    images_html: str = "",
    footer: str = "",
) -> EmailContent:
    """Soạn thư gửi khách kèm chi tiết hóa đơn.

    `amount_due` tách khỏi `total` vì hóa đơn có thể đã thu một phần — gửi lại mà vẫn ghi
    nguyên tổng là đòi khách trả hai lần phần họ đã chuyển.

    `project_name` là tên dự án (deal) mà hóa đơn này thuộc về. Hóa đơn chỉ ghi tên hạng mục và
    số tiền; khách làm nhiều dự án với cùng một freelancer thì không biết thư này nói về dự án nào.

    Tiêu đề **cố ý không gắn tiền tố `[SoloDesk]`**, giống `reminders.build_subject`: đây là
    freelancer gửi cho khách của mình, không phải hệ thống thông báo. Gắn tên phần mềm vào
    là lộ ra rằng máy gửi.

    Mọi giá trị đều `escape()`: tên khách, nhãn hạng mục và ghi chú đều do người dùng gõ, chỉ
    một dấu `&` hay `<` là vỡ HTML của thư gửi khách.  #Huynh
    """
    sender = (freelancer_name or "").strip()
    project = (project_name or "").strip()
    about = f' cho dự án "{project}"' if project else ""
    subject = f"Hóa đơn {invoice_number}" + (f" từ {sender}" if sender else "")

    # Bỏ dòng tên nội bộ TRƯỚC mọi bước sau: khách không thấy dòng đó, nên nó cũng không có lý do gì
    # để góp mặt vào việc điền số hay kiểm số bên dưới.
    notes = strip_invoice_title_line(notes)

    # Điền số TRƯỚC khi escape/đưa vào thư: số trong lời nhắn luôn là số cần trả của chính
    # hóa đơn này (`amount_due`), khớp bảng bên trên và mã QR.
    notes = fill_amount_placeholder(notes, amount_due)

    # CHẶN gửi khi lời nhắn ghi một số tiền không khớp hóa đơn. Số do người dùng gõ tay là chuyện
    # tự do, nhưng thư tới khách mà mang hai tổng khác nhau (bảng một số, lời nhắn một số) thì
    # khách chuyển theo chữ và hóa đơn thành "thanh toán một phần". Số khớp bất kỳ con số nào trên
    # hóa đơn (tổng, tạm tính, thuế, từng hạng mục) thì cho qua — chỉ số LẠ mới bị chặn.  #Huynh
    subtotal = sum((amount for _, amount in line_items), Decimal(0))
    allowed = [round(total), round(amount_due), round(subtotal), *(round(a) for _, a in line_items)]
    if total > subtotal:
        allowed.append(round(total - subtotal))  # tiền thuế
    wrong = mismatched_amounts(notes, allowed)
    if wrong:
        raise BusinessRuleError(
            "Lời nhắn gửi khách đang ghi số tiền "
            + ", ".join(format_vnd(a) for a in wrong)
            + f" khác với số tiền của hóa đơn ({format_vnd(total)}). Hãy xem xét lại cho khớp "
            "trước khi gửi."
        )

    partially_paid = amount_due != total
    due_label = "Còn phải thanh toán" if partially_paid else "Tổng cộng"

    # ---- bản chữ thuần ----------------------------------------------------------------
    plain_lines = [
        f"Chào {client_name},",
        "",
        (
            f"{sender} gửi bạn hóa đơn {invoice_number}{about}."
            if sender
            else f"Đây là hóa đơn {invoice_number}{about}."
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

    about_html = f' cho dự án <strong>"{escape(project)}"</strong>' if project else ""
    intro = (
        f"<strong>{escape(sender)}</strong> gửi bạn hóa đơn "
        f"<strong>{escape(invoice_number)}</strong>{about_html}."
        if sender
        else f"Đây là hóa đơn <strong>{escape(invoice_number)}</strong>{about_html}."
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
