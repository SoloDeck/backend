"""Nhận ra SỐ TIỀN do người dùng gõ tay trong lời nhắn gửi khách (ghi chú hóa đơn).

Lời nhắn là văn bản tự do, nên freelancer gõ được "Tổng số tiền cần thanh toán là 511.900.000 ₫"
trong khi hóa đơn thật là 521.900.000 ₫. Thư tới khách mang hai tổng khác nhau; khách chuyển theo
chữ thì hóa đơn thành "thanh toán một phần" và nợ treo. Hàm ở đây chỉ làm MỘT việc: tìm các số
trông như tiền để chỗ gọi so với số tiền thật của hóa đơn.

Cố ý hẹp: chỉ coi là tiền khi có DẤU PHÂN CÁCH NGHÌN (`511.900.000`) hoặc ĐƠN VỊ tiền đi kèm
(`500k`, `30tr`, `1,5 triệu`, `50.000đ`, `2 tỷ`). Số trần ("0352015349", "16/10/2026", "đợt 2",
"50%", mã "INV-20261003-AB12") KHÔNG phải tiền — không thì mọi số điện thoại, ngày tháng đều bị
chặn.

Bản TypeScript tương ứng ở web (`invoiceComposer.ts`, `findMoneyAmounts`) phải cho CÙNG kết quả;
hai bên dùng chung bộ ví dụ trong test.  #Huynh
"""

import re
import unicodedata

# Hệ số quy về đồng. Các đơn vị dài đứng trước đơn vị ngắn để khớp đúng ("triệu" trước "tr").
_UNIT_FACTORS = {
    "₫": 1,
    "vnđ": 1,
    "vnd": 1,
    "đồng": 1,
    "dong": 1,
    "nghìn": 1_000,
    "nghin": 1_000,
    "ngàn": 1_000,
    "ngan": 1_000,
    "triệu": 1_000_000,
    "trieu": 1_000_000,
    "tỷ": 1_000_000_000,
    "tỉ": 1_000_000_000,
    "ty": 1_000_000_000,
    "đ": 1,
    "tr": 1_000_000,
    "k": 1_000,
}
_UNITS = "|".join(re.escape(unit) for unit in _UNIT_FACTORS)

# - không bắt đầu giữa một số khác (`(?<![\d.,])`);
# - nhánh 1: số có dấu phân cách nghìn (`511.900.000`, `1,500`), không dính thêm chữ số;
# - nhánh 2: số trần/thập phân, chỉ tính là tiền nếu có đơn vị đi kèm;
# - đơn vị phải đứng riêng ("5km", "5 trang" không phải "5k", "5 tr").
_MONEY_RE = re.compile(
    rf"(?<![\d.,])(\d{{1,3}}(?:[.,]\d{{3}})+(?!\d)|\d+(?:[.,]\d+)?)\s*({_UNITS})?(?![^\W\d_]|\d)",
    re.IGNORECASE,
)


def find_money_amounts(text: str | None) -> list[int]:
    """Các số tiền (đồng, làm tròn) nhìn thấy trong `text`, theo thứ tự xuất hiện."""
    if not text:
        return []
    amounts: list[int] = []
    # NFC: chữ có dấu gõ dạng tổ hợp (e + dấu) vẫn khớp đơn vị như "triệu".
    for match in _MONEY_RE.finditer(unicodedata.normalize("NFC", text)):
        number, unit = match.group(1), (match.group(2) or "").lower()
        has_thousands_separator = bool(re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", number))
        if not has_thousands_separator and not unit:
            continue  # số trần: điện thoại, ngày tháng, số thứ tự... không phải tiền
        value = (
            float(number.replace(".", "").replace(",", ""))
            if has_thousands_separator
            else float(number.replace(",", "."))
        )
        amounts.append(round(value * _UNIT_FACTORS.get(unit, 1)))
    return amounts


def mismatched_amounts(text: str | None, allowed: list[int], *, tolerance: int = 1) -> list[int]:
    """Số tiền trong `text` KHÔNG khớp số nào trong `allowed` (lệch quá `tolerance` đồng)."""
    return [
        amount
        for amount in find_money_amounts(text)
        if not any(abs(amount - ok) <= tolerance for ok in allowed)
    ]
