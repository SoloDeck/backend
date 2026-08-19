"""Khối "Thanh toán cho tôi" nhúng vào thư nhắc thanh toán.

Vì sao tồn tại: Phiếu SU26SE083 (dòng 140) đòi "chuỗi nhắc thanh toán MoMo/chuyển khoản" —
nêu đây là thứ HubSpot/Zoho không có. Thư nhắc trước đây chỉ có nội dung + chữ ký, khách đọc
xong không biết chuyển tiền vào đâu nên phải nhắn hỏi lại; đúng cái ma sát phiếu muốn xoá.

Bố cục, câu chữ và màu lấy từ mẫu `reminder_due_soon.html` của lead, nhưng **chuyển thể cho
email**:
  - mẫu dùng flexbox → Outlook (engine Word) không hiểu, phải dựng bằng `<table>`;
  - mẫu có nút "sao chép" chạy bằng JavaScript → mail không chạy JS, bỏ;
  - mẫu nhúng QR kiểu `data:image/png;base64` → Gmail CẮT BỎ ảnh dạng đó, nên đường email
    trả PNG ra ngoài để đính kèm dạng `cid:`, còn đường xem-trước-trên-web mới dùng data-URI.

Toàn bộ file là hàm THUẦN (không I/O, không DB) — test được câu chữ và chuỗi QR mà không cần
SMTP hay mạng.  #Huynh
"""

from dataclasses import dataclass
from decimal import Decimal
from html import escape

import structlog

log = structlog.get_logger(__name__)

# Mã tiền tệ và mã quốc gia theo ISO — VietQR chỉ dùng cho tài khoản VN, tiền VND.
_CURRENCY_VND = "704"
_COUNTRY_VN = "VN"
# Định danh dịch vụ chuyển nhanh NAPAS 247 trong chuỗi VietQR.
_NAPAS_GUID = "A000000727"
_SERVICE_TRANSFER_TO_ACCOUNT = "QRIBFTTA"


@dataclass(frozen=True)
class PaymentInfo:
    """Thông tin nhận tiền của freelancer, đọc từ hồ sơ."""

    bank_code: str | None = None
    bank_name: str | None = None
    account_number: str | None = None
    account_holder: str | None = None
    momo_phone: str | None = None
    note: str | None = None

    @property
    def has_bank(self) -> bool:
        return bool(self.bank_code and self.account_number)

    @property
    def has_anything(self) -> bool:
        return bool(self.has_bank or self.momo_phone)


def _tlv(tag: str, value: str) -> str:
    """Một ô EMVCo: mã 2 ký tự + độ dài 2 chữ số + giá trị."""
    return f"{tag}{len(value):02d}{value}"


def crc16_ccitt(data: str) -> str:
    """CRC-16/CCITT-FALSE — chuẩn EMVCo bắt buộc ở cuối chuỗi QR.

    Sai CRC thì app ngân hàng từ chối quét, mà lỗi đó KHÔNG hiện ra ở đâu cho tới lúc khách
    thật đứng quét. Nên có test giải mã ngược lại chuỗi này.  #Huynh
    """
    crc = 0xFFFF
    for byte in data.encode("utf-8"):
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return f"{crc:04X}"


def vietqr_payload(
    *,
    bank_code: str,
    account_number: str,
    amount: Decimal | int | None = None,
    memo: str | None = None,
) -> str:
    """Chuỗi VietQR (EMVCo) để app ngân hàng quét ra sẵn người nhận, số tiền, nội dung.

    Tự dựng thay vì gọi dịch vụ sinh ảnh bên ngoài: số tài khoản và số tiền là dữ liệu
    nhạy cảm, không có lý do gì để nó đi qua máy chủ của người khác.
    """
    account_info = _tlv("00", _NAPAS_GUID) + _tlv(
        "01", _tlv("00", bank_code) + _tlv("01", account_number)
    )

    parts = [
        _tlv("00", "01"),  # phiên bản
        # 12 = QR dùng một lần (đã gắn số tiền), 11 = dùng nhiều lần.
        _tlv("01", "12" if amount else "11"),
        _tlv("38", account_info + _tlv("02", _SERVICE_TRANSFER_TO_ACCOUNT)),
        _tlv("53", _CURRENCY_VND),
    ]
    if amount:
        parts.append(_tlv("54", str(int(amount))))
    parts.append(_tlv("58", _COUNTRY_VN))
    if memo:
        # Nội dung chuyển khoản: cắt 25 ký tự cho vừa giới hạn của phần lớn ngân hàng.
        parts.append(_tlv("62", _tlv("08", memo[:25])))

    body = "".join(parts) + "6304"
    return body + crc16_ccitt(body)


def render_qr_png(payload: str, scale: int = 5) -> bytes | None:
    """PNG của mã QR, hoặc `None` nếu môi trường chưa có thư viện sinh QR.

    Import BÊN TRONG hàm, không đặt ở đầu file: `payment_block` được `delivery_service`
    import, nên thiếu `segno` mà để import ở đầu là **cả module nhắc nhở sập** — đã dính
    thật, endpoint xem trước trả 500 vì container chưa cài gói này. Thư kèm số tài khoản
    dạng chữ vẫn dùng được; mất mã QR chỉ là bất tiện, mất cả lá thư mới là hỏng.  #Huynh
    """
    import io

    try:
        import segno
    except ImportError:  # pragma: no cover - phụ thuộc môi trường
        log.warning("payment_block.qr_unavailable", reason="segno chưa được cài")
        return None

    buffer = io.BytesIO()
    segno.make(payload, error="m").save(buffer, kind="png", scale=scale, border=2)
    return buffer.getvalue()


def _row(label: str, value: str) -> str:
    return (
        '<tr>'
        f'<td style="padding:3px 12px 3px 0;color:#6b7280;font-size:12px;white-space:nowrap">'
        f"{escape(label)}</td>"
        f'<td style="padding:3px 0;font-size:13px;font-weight:600;color:#111827">'
        f"{escape(value)}</td>"
        "</tr>"
    )


def build_payment_block(
    info: PaymentInfo,
    *,
    amount: Decimal | int | None = None,
    memo: str | None = None,
    qr_src: str = "cid:vietqr",
    with_qr: bool = True,
) -> tuple[str, str, bytes | None]:
    """Trả `(html, plain, qr_png)`.

    `qr_png` là `None` khi chưa khai ngân hàng — lúc đó thư vẫn có phần MoMo nếu có. Chưa
    khai gì cả thì trả rỗng và thư gửi y như cũ, KHÔNG chèn một khung trống.

    Phần chữ LUÔN được in song song với mã QR: rất nhiều trình đọc mail chặn ảnh theo mặc
    định, mà thư chỉ có mỗi cái ảnh thì coi như không nói gì.

    `with_qr=False` giữ nguyên phần chữ nhưng bỏ hẳn ảnh QR. Dùng khi freelancer đã tự đính
    ảnh mã QR của mình vào thư: hai mã QR cạnh nhau là khách phải phân vân quét cái nào, mà
    đoán sai thì tiền đi nhầm chỗ.  #Huynh
    """
    if not info.has_anything:
        return "", "", None

    amount_text = f"{int(amount):,} ₫".replace(",", ".") if amount else None

    rows: list[tuple[str, str]] = []
    plain_lines: list[str] = ["THANH TOÁN CHO TÔI"]
    qr_png: bytes | None = None

    if info.has_bank:
        assert info.bank_code and info.account_number
        if with_qr:
            qr_png = render_qr_png(
                vietqr_payload(
                    bank_code=info.bank_code,
                    account_number=info.account_number,
                    amount=amount,
                    memo=memo,
                )
            )
        rows.append(("Ngân hàng", info.bank_name or info.bank_code))
        rows.append(("Số tài khoản", info.account_number))
        if info.account_holder:
            rows.append(("Chủ tài khoản", info.account_holder))
        if amount_text:
            rows.append(("Số tiền", amount_text))
        if memo:
            rows.append(("Nội dung CK", memo))

    if info.momo_phone:
        rows.append(("MoMo", info.momo_phone))

    if info.note:
        rows.append(("Ghi chú", info.note))

    plain_lines += [f"- {label}: {value}" for label, value in rows]
    if qr_png is not None:
        plain_lines.append("(Thư bản HTML có kèm mã QR VietQR quét là điền sẵn số tiền.)")

    qr_cell = (
        f'<td style="padding-right:16px;vertical-align:top">'
        f'<img src="{escape(qr_src, quote=True)}" alt="Mã VietQR" '
        'width="132" height="132" style="display:block;border:0"></td>'
        if qr_png is not None
        else ""
    )

    html = (
        '<table role="presentation" cellpadding="0" cellspacing="0" '
        'style="width:100%;margin:20px 0;border:1px solid #E5E7EB;border-radius:10px;'
        'background:#F9FAFB">'
        '<tr><td style="padding:14px 16px">'
        '<div style="font-size:11px;font-weight:700;letter-spacing:.4px;'
        'text-transform:uppercase;color:#059669;margin-bottom:10px">'
        f"{'Quét để thanh toán · VietQR' if qr_png is not None else 'Thanh toán cho tôi'}</div>"
        '<table role="presentation" cellpadding="0" cellspacing="0"><tr>'
        f"{qr_cell}"
        '<td style="vertical-align:top"><table role="presentation" cellpadding="0" '
        f'cellspacing="0">{"".join(_row(k, v) for k, v in rows)}</table></td>'
        "</tr></table>"
        + (
            '<div style="margin-top:10px;padding-top:8px;border-top:1px solid #E5E7EB;'
            'font-size:11px;color:#6b7280">'
            "Khi quét QR, số tiền và nội dung chuyển khoản được điền sẵn.</div>"
            if qr_png is not None
            else ""
        )
        + "</td></tr></table>"
    )

    return html, "\n".join(plain_lines), qr_png


# --- Nối vào luồng gửi thư -------------------------------------------------------------
#
# Chỉ hai loại nhắc dưới đây mới kèm thông tin thanh toán. Gắn số tài khoản vào thư "hỏi
# thăm dự án" hay "lâu rồi chưa liên lạc" là sai ngữ cảnh — đọc lên như đi đòi nợ.  #Huynh
PAYMENT_REMINDER_TYPES = frozenset({"payment_due", "payment_overdue"})


def payment_info_from_owner(owner: object) -> PaymentInfo:
    """Bóc thông tin nhận tiền từ hồ sơ freelancer."""
    return PaymentInfo(
        bank_code=getattr(owner, "bank_code", None),
        bank_name=getattr(owner, "bank_code", None),
        account_number=getattr(owner, "bank_account_number", None),
        account_holder=getattr(owner, "bank_account_holder", None),
        momo_phone=getattr(owner, "momo_phone_number", None),
        note=getattr(owner, "bank_account_info", None),
    )


async def resolve_amount_and_memo(
    db: object, reminder: object, label: str | None
) -> tuple[Decimal | None, str | None]:
    """Số tiền và nội dung chuyển khoản, suy từ thứ mà lời nhắc đang trỏ tới.

    - `invoice` → phần còn nợ của hoá đơn, nội dung là số hoá đơn (khách đối chiếu sổ sách);
    - `deal`    → tổng các mốc thanh toán CHƯA THU, dùng lại đúng bộ tính tiền của bảng
      doanh thu (`milestone_money`) — một luật tính tiền cho cả hệ thống, không đẻ luật thứ hai;
    - còn lại   → không có số tiền; QR vẫn hợp lệ, khách tự nhập.
    """
    from sqlalchemy import select

    from src.infrastructure.database.models import InvoiceModel

    target_type = getattr(reminder, "target_type", None)
    target_id = getattr(reminder, "target_id", None)
    owner_id = getattr(reminder, "owner_user_id", None)

    if target_type == "invoice":
        invoice = await db.scalar(  # type: ignore[attr-defined]
            select(InvoiceModel).where(
                InvoiceModel.id == target_id,
                InvoiceModel.owner_user_id == owner_id,
            )
        )
        if invoice is None:
            return None, label
        remaining = Decimal(invoice.total or 0) - Decimal(invoice.amount_paid or 0)
        memo = getattr(invoice, "invoice_number", None) or label
        return (remaining if remaining > 0 else None), memo

    if target_type == "deal":
        from src.modules.analytics.application.milestone_money import totals
        from src.modules.analytics.infrastructure.repository import AnalyticsRepository

        rows = await AnalyticsRepository(db).milestone_rows(owner_id)  # type: ignore[arg-type]
        for deal in rows:
            if deal["deal_id"] == target_id:
                from src.modules.analytics.application.service import AnalyticsService

                money = totals(AnalyticsService._milestones_of(deal))
                return (money.outstanding if money.outstanding > 0 else None), label
        return None, label

    return None, label


async def build_payment_section(
    db: object, reminder: object, owner: object, label: str | None
) -> tuple[str, str, bytes | None]:
    """Khối thanh toán cho MỘT lời nhắc — rỗng nếu không phải loại nhắc tiền."""
    if getattr(reminder, "reminder_type", None) not in PAYMENT_REMINDER_TYPES:
        return "", "", None
    if owner is None:
        return "", "", None

    # Tra số tiền là BEST-EFFORT. Hỏng ở đây (deal chưa có project, dữ liệu cũ, DB trục
    # trặc) thì vẫn phải gửi được thư kèm số tài khoản — khách tự điền số tiền còn hơn
    # freelancer không đòi được đồng nào vì thư không đi.  #Huynh
    try:
        amount, memo = await resolve_amount_and_memo(db, reminder, label)
    except Exception as exc:  # noqa: BLE001
        log.warning("reminder.payment_amount_failed", error=str(exc))
        amount, memo = None, label

    return build_payment_block(payment_info_from_owner(owner), amount=amount, memo=memo)
