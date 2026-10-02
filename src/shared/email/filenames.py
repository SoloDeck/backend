"""Đặt tên file đính kèm email."""

import re
import unicodedata

# Tên file không nên dài: nhiều trình đọc mail tự cắt, và tên quá dài cũng chẳng giúp gì.
_MAX_STEM_LENGTH = 60


def attachment_filename(prefix: str, label: str | None, *, ext: str = "pdf") -> str:
    """`("bao-gia", "Website đặt lịch phòng khám")` → `"bao-gia-website-dat-lich-phong-kham.pdf"`.

    Chỉ ra chữ thường không dấu, số và dấu gạch ngang. Khách mở thư bằng trình đọc mail nào
    cũng thấy tên file đọc được, và lưu về máy không dính ký tự lạ — tên có dấu tiếng Việt
    trong header là nơi nhiều trình đọc cũ hiện ra chuỗi rác.

    `label` trống (hoặc toàn ký tự đặc biệt) thì chỉ còn `prefix`: vẫn là một tên hợp lệ.
    """
    folded = unicodedata.normalize("NFKD", (label or "").replace("đ", "d").replace("Đ", "D"))
    ascii_only = folded.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_only).strip("-")[:_MAX_STEM_LENGTH].strip("-")
    stem = f"{prefix}-{slug}" if slug else prefix
    return f"{stem}.{ext}"
