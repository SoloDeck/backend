"""Đọc số tiền đồng thành chữ tiếng Việt: 12.000.000 -> "Mười hai triệu đồng Việt Nam".

Hợp đồng Việt Nam ghi số tiền hai lần: bằng số và "bằng chữ". Bản trước để AI tự viết phần chữ,
mà model đọc sai số tiền được (và từng viết một lịch thanh toán không khớp báo giá), nên giờ làm
bằng code: cùng một con số luôn ra cùng một câu chữ.  #Huynh
"""

_DIGITS = ("không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín")
_GROUP_UNITS = ("", "nghìn", "triệu")
_BILLION = 1_000_000_000


def _read_group(value: int, *, has_higher_group: bool) -> str:
    """Đọc một nhóm ba chữ số (0-999).

    `has_higher_group`: phía trước còn nhóm khác khác 0. Khi đó hàng trăm bằng 0 vẫn phải đọc
    ("một nghìn không trăm linh năm"), còn nhóm đứng đầu thì không ("năm", "mười hai").
    """
    hundreds, tens, ones = value // 100, (value // 10) % 10, value % 10
    words: list[str] = []

    if hundreds > 0 or has_higher_group:
        words.append(f"{_DIGITS[hundreds]} trăm")

    if tens > 1:
        words.append(f"{_DIGITS[tens]} mươi")
        if ones == 1:
            words.append("mốt")
        elif ones == 5:
            words.append("lăm")
        elif ones > 0:
            words.append(_DIGITS[ones])
    elif tens == 1:
        words.append("mười")
        if ones == 5:
            words.append("lăm")
        elif ones > 0:
            words.append(_DIGITS[ones])
    elif ones > 0:
        if hundreds > 0 or has_higher_group:
            words.append("linh")
        words.append(_DIGITS[ones])

    return " ".join(words)


def _read_below_billion(value: int, *, after_higher: bool = False) -> str:
    """`after_higher`: phía trước (ở bậc tỷ) còn phần khác 0, nên nhóm đầu cũng đọc đủ hàng trăm."""
    groups = [(value // 1_000_000) % 1000, (value // 1000) % 1000, value % 1000]
    words: list[str] = []
    for index, group in enumerate(groups):
        if group == 0:
            continue
        has_higher = after_higher or any(groups[:index])
        words.append(_read_group(group, has_higher_group=has_higher))
        unit = _GROUP_UNITS[2 - index]
        if unit:
            words.append(unit)
    return " ".join(words)


def number_in_words(value: int) -> str:
    """Số nguyên dương thành chữ thường, không kèm đơn vị. 0 hoặc âm -> chuỗi rỗng."""
    if value <= 0:
        return ""
    if value < _BILLION:
        return _read_below_billion(value)

    # Từ một tỷ trở lên: đọc phần tỷ như một số riêng (để "mười nghìn tỷ" vẫn ra đúng) rồi nối
    # phần lẻ.
    billions, rest = divmod(value, _BILLION)
    head = f"{number_in_words(billions)} tỷ"
    return f"{head} {_read_below_billion(rest, after_higher=True)}" if rest else head


def vnd_in_words(amount: int) -> str:
    """"Mười hai triệu đồng Việt Nam" — chữ cái đầu viết hoa. Số không dương -> chuỗi rỗng."""
    words = number_in_words(int(amount))
    if not words:
        return ""
    return f"{words[0].upper()}{words[1:]} đồng Việt Nam"
