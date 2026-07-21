"""Danh mục NGHỀ của freelancer — dữ liệu tĩnh + ĐƯỜNG NỐI (seam) duy nhất.

Dùng cho: freelancer chọn nghề của mình (gói 2), và đưa TÊN NGHỀ vào prompt lead
qualifier làm ngữ cảnh chấm điểm (gói 3). CỐ TÌNH không kèm bộ câu hỏi theo nghề —
bản gốc (#72 trên main) làm thế và kéo theo retriever chạy model tại máy (torch);
ở đây chỉ giữ đúng "nghề là gì", không rước nặng.

ĐƯỜNG NỐI (seam): mọi nơi khác trong hệ thống chỉ được chạm tới nghề QUA các hàm ở
file này (`all_professions`, `is_valid_profession`, `profession_label`) — KHÔNG đọc
thẳng dict `_PROFESSIONS`. Nhờ vậy sau này khi Admin cần quản lý nghề (kèm feature
"thư viện mẫu theo nghề" — Gói 6 của Phiếu), chỉ cần đổi RUỘT ba hàm này từ đọc dict
sang query bảng DB; users / lead_qualifier / mẫu KHÔNG phải sửa một dòng.  #Huynh
"""

from __future__ import annotations

# slug (kebab-case, không dấu — an toàn khi lưu DB / so khớp) -> nhãn tiếng Việt.
# dict giữ thứ tự chèn nên FE nhận danh sách theo đúng thứ tự này.
# Để "riêng tư" (tiền tố _) để ép mọi truy cập đi qua các hàm bên dưới — giữ seam sạch.
_PROFESSIONS: dict[str, str] = {
    "software-development": "Lập trình / Phát triển phần mềm",
    "ui-ux-design": "Thiết kế UI/UX",
    "graphic-design": "Thiết kế đồ hoạ",
    "digital-marketing": "Tư vấn Digital Marketing",
    "content-writing": "Viết nội dung / Copywriter",
    "photography-videography": "Nhiếp ảnh & Quay dựng video",
}


def all_professions() -> list[dict[str, str]]:
    """Danh sách nghề cho FE đổ dropdown: ``[{"value": slug, "label": nhãn}, ...]``."""
    return [{"value": value, "label": label} for value, label in _PROFESSIONS.items()]


def is_valid_profession(value: str | None) -> bool:
    """Slug có nằm trong danh mục không. ``None`` = chưa chọn nghề, vẫn hợp lệ."""
    return value is None or value in _PROFESSIONS


def profession_label(value: str | None) -> str | None:
    """Nhãn tiếng Việt của một slug; ``None`` nếu chưa chọn / không tồn tại."""
    return _PROFESSIONS.get(value) if value else None
