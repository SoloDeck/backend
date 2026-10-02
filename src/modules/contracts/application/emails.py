"""Nội dung email gửi HỢP ĐỒNG cho khách của freelancer.

Hàm THUẦN (không I/O, không DB) — cùng lối với `proposals/application/emails.py`.

**Thư này chỉ là phong bì; tờ hợp đồng là file PDF đính kèm.** Khách không có tài khoản
SoloDesk và không ký trong hệ thống: hai bên ký ở ngoài (in ra ký tay, ký scan, nhắn qua
Zalo) rồi freelancer vào ghi nhận. Nên thân thư phải nói rõ việc khách cần làm tiếp: đọc,
ký, gửi lại — chứ không phải "bấm vào đây để ký".  #Huynh
"""

from dataclasses import dataclass
from html import escape


@dataclass(frozen=True)
class EmailContent:
    subject: str
    html: str
    plain: str


def build_contract_email(
    *,
    client_name: str,
    freelancer_name: str | None,
    project_name: str | None,
    contract_number: str | None = None,
    footer: str = "",
) -> EmailContent:
    """Soạn thư gửi khách kèm hợp đồng (file PDF đính kèm do chỗ gọi lo).

    `contract_number` lấy từ chính tờ hợp đồng (`ContractDocument.contract_number`) để khách
    có một mã chung mà nhắc tới khi trao đổi; trống thì bỏ đi.

    Tiêu đề **cố ý không gắn tiền tố `[SoloDesk]`**: đây là freelancer gửi cho khách của
    mình, không phải thư hệ thống.

    Mọi giá trị đều `escape()` vì do người dùng gõ.  #Huynh
    """
    sender = (freelancer_name or "").strip()
    project = (project_name or "").strip()
    number = (contract_number or "").strip()

    subject = f"Hợp đồng dự án {project}" if project else "Hợp đồng dịch vụ"
    if sender:
        subject += f" từ {sender}"

    who = sender or "Chúng tôi"
    about = f'dự án "{project}"' if project else "dịch vụ"
    number_text = f" (số {number})" if number else ""
    ask = (
        "Vui lòng đọc kỹ hợp đồng trong file PDF đính kèm. Nếu đồng ý, bạn ký rồi gửi lại "
        "bản đã ký bằng cách trả lời thẳng email này. Cần chỉnh điều khoản nào, cứ nói trong "
        "thư trả lời."
    )

    # ---- bản chữ thuần ----------------------------------------------------------------
    plain_lines = [
        f"Chào {client_name},",
        "",
        f"{who} gửi bạn hợp đồng cho {about}{number_text}.",
        "",
        ask,
    ]
    if footer:
        plain_lines += ["", footer]

    # ---- bản HTML ---------------------------------------------------------------------
    footer_block = (
        f'<p style="color:#6b7280;font-size:13px;white-space:pre-line;">{escape(footer)}</p>'
        if footer
        else ""
    )
    html = (
        '<div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;'
        'line-height:1.6;color:#111827;">'
        f"<p>Chào {escape(client_name)},</p>"
        f"<p><strong>{escape(who)}</strong> gửi bạn hợp đồng cho "
        f"{escape(about)}{escape(number_text)}.</p>"
        f"<p>{escape(ask)}</p>"
        f"{footer_block}"
        "</div>"
    )

    return EmailContent(subject=subject, html=html, plain="\n".join(plain_lines))
