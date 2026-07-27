"""Danh mục NGHỀ của freelancer — dữ liệu tĩnh + ĐƯỜNG NỐI (seam) duy nhất.

Dùng cho: freelancer chọn nghề của mình (gói 2), và đưa TÊN NGHỀ vào prompt lead
qualifier làm ngữ cảnh chấm điểm (gói 3). CỐ TÌNH không kèm bộ câu hỏi theo nghề —
bản gốc (#72 trên main) làm thế và kéo theo retriever chạy model tại máy (torch);
ở đây chỉ giữ đúng "nghề là gì", không rước nặng.

ĐƯỜNG NỐI (seam): mọi nơi khác trong hệ thống chỉ được chạm tới nghề QUA các hàm ở
file này (`all_professions`, `is_valid_profession`, `profession_label`,
`profession_scam_hint`) — KHÔNG đọc thẳng dict nội bộ. Nhờ vậy sau này khi Admin cần
quản lý nghề (kèm feature "thư viện mẫu theo nghề" — Gói 6 của Phiếu), chỉ cần đổi RUỘT
các hàm này từ đọc dict sang query bảng DB; users / lead_qualifier / mẫu KHÔNG phải sửa
một dòng.  #Huynh
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


# Mẫu LỪA ĐẢO thường gặp theo từng nghề. Lead qualifier đọc qua `profession_scam_hint`
# để đối chiếu với lời khách rồi đưa vào `red_flags` NẾU khớp — KHÔNG phải để bịa cờ đỏ
# khi khách không có dấu hiệu. Đây là "kiến thức theo nghề" bản NHẸ (thay cho retriever
# torch đã bỏ): chỉ vài dòng text tĩnh, chèn đúng nghề của freelancer vào prompt.  #Huynh
_PROFESSION_SCAM_HINTS: dict[str, str] = {
    "software-development": (
        "đòi bàn giao source code / deploy trước khi thanh toán; kiểu 'làm xong app rồi "
        "mới trả tiền'; yêu cầu dựng bản demo đầy đủ tính năng miễn phí để 'duyệt'; hứa "
        "dự án lớn dài hạn nếu làm task đầu không công"
    ),
    "ui-ux-design": (
        "đòi thiết kế vài mẫu / concept miễn phí rồi mới chọn (thi thiết kế trá hình); "
        "xin file nguồn trước khi thanh toán; 'làm thử một màn hình xem hợp không' không công"
    ),
    "graphic-design": (
        "'gửi vài mẫu logo để chọn' miễn phí; đòi file gốc (AI/PSD) trước khi trả tiền; "
        "lấy bản nháp có watermark rồi biến mất"
    ),
    "digital-marketing": (
        "trả theo KPI/kết quả nhưng không đặt cọc; đòi quyền admin tài khoản quảng cáo / "
        "fanpage trước khi thanh toán; hứa chia % hoa hồng thay vì trả phí"
    ),
    "content-writing": (
        "'viết thử vài bài test' không công; đòi nộp bài hoàn chỉnh trước khi chốt; gom "
        "'bài mẫu' của nhiều ứng viên thành nội dung dùng thật"
    ),
    "photography-videography": (
        "chụp/quay xong sự kiện mới thanh toán, không đặt cọc; giữ toàn bộ file gốc làm "
        "điều kiện; 'chụp thử buổi này miễn phí để xem chất lượng'"
    ),
}


def profession_scam_hint(value: str | None) -> str | None:
    """Mẫu lừa đảo thường gặp của một nghề (để AI cảnh báo freelancer).

    ``None`` nếu chưa chọn nghề / nghề không có trong danh mục — khi đó lead qualifier
    chỉ dùng các cờ đỏ chung, không có gợi ý đặc thù nghề.
    """
    return _PROFESSION_SCAM_HINTS.get(value) if value else None
