"""Kiểm tra sơ bộ địa chỉ email trước khi đưa cho SMTP."""

import re

# KHÔNG cố bao hết RFC 5322 — chỉ chặn những thứ CHẮC CHẮN không gửi được, để báo lỗi rõ ràng
# TRƯỚC khi chốt trạng thái và dựng PDF: thiếu `@`, thiếu dấu chấm trong tên miền (`a@b`),
# hai địa chỉ dính nhau (`a@x.com, b@y.com`), dạng `Tên <a@b.com>`, chữ có dấu ở phần trước `@`.
# Những ca đó mà để lọt xuống SMTP thì người dùng chỉ nhận câu "lỗi hệ thống thư" chung chung,
# dù thử lại bao nhiêu lần cũng vô ích.  #Huynh
_PLAUSIBLE_EMAIL = re.compile(
    r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+"
    r"@(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
    r"[A-Za-z][A-Za-z0-9-]{1,62}"
)


def looks_like_email(value: str) -> bool:
    """`True` nếu `value` có dạng một địa chỉ email gửi được (chưa kiểm hộp thư có tồn tại)."""
    return bool(_PLAUSIBLE_EMAIL.fullmatch(value.strip()))
