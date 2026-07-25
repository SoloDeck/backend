"""Danh mục NGHỀ của freelancer — dữ liệu tĩnh + ĐƯỜNG NỐI (seam) duy nhất.

Dùng cho: freelancer chọn nghề của mình, bộ câu hỏi theo nghề của intake form, và đưa
TÊN NGHỀ + mẫu lừa đảo đặc thù vào prompt lead qualifier làm ngữ cảnh chấm điểm.

Slug (`value`) trùng TÊN THƯ MỤC dưới `src/ai/knowledge/professions/`, nên `profession`
mà khách gửi lên đi thẳng vào retriever của lead qualifier để tra kiến thức theo nghề.
Đừng đổi slug ở đây mà không đổi tên thư mục tương ứng.

ĐƯỜNG NỐI (seam): mọi nơi khác trong hệ thống chỉ được chạm tới nghề QUA các hàm ở
file này (`all_professions`, `is_valid_profession`, `profession_label`,
`profession_scam_hint`, `required_field_keys`) — KHÔNG đọc thẳng dict nội bộ. Nhờ vậy
sau này khi Admin cần quản lý nghề, chỉ cần đổi RUỘT các hàm này từ đọc dict sang query
bảng DB; users / lead_qualifier / mẫu KHÔNG phải sửa một dòng.  #Huynh
"""

from __future__ import annotations

from typing import TypedDict


class ProfessionFieldDef(TypedDict):
    field_key: str
    label: str
    field_type: str  # "text" | "select" | "multiselect"
    options: list[str] | None
    is_required: bool


class ProfessionDef(TypedDict):
    value: str
    label: str
    fields: list[ProfessionFieldDef]


def _field(
    field_key: str,
    label: str,
    field_type: str = "text",
    options: list[str] | None = None,
    required: bool = True,
) -> ProfessionFieldDef:
    return {
        "field_key": field_key,
        "label": label,
        "field_type": field_type,
        "options": options,
        "is_required": required,
    }


# `label` là nhãn tiếng Việt hiển thị cho freelancer VÀ là chuỗi đưa vào prompt lead
# qualifier. Nhãn của từng CÂU HỎI bên trong `fields` vẫn giữ tiếng Anh như bản trên
# main — dịch nốt là việc riêng, không gộp vào lần merge này.  #Huynh
PROFESSIONS: list[ProfessionDef] = [
    {
        "value": "software-developer",
        "label": "Lập trình / Phát triển phần mềm",
        "fields": [
            _field(
                "project_type",
                "Project type",
                "select",
                [
                    "Website", "Web app", "Mobile app", "API/backend", "E-commerce",
                    "Booking system", "CRM/internal tool", "Dashboard", "SaaS",
                    "Automation", "Other",
                ],
            ),
            _field("business_goal", "Business goal", "text"),
            _field(
                "target_users",
                "Target users",
                "select",
                ["Customers", "Employees", "Admins", "Partners", "Students", "Patients", "Other"],
            ),
            _field(
                "platforms_needed",
                "Platforms needed",
                "select",
                ["Web", "Android", "iOS", "Both mobile platforms", "Desktop", "API/backend only"],
            ),
            _field(
                "core_features",
                "Core features",
                "multiselect",
                [
                    "Login", "Booking", "Payments", "Inventory", "Reports", "Notifications",
                    "Chat", "File upload", "Search", "Admin dashboard", "Other",
                ],
            ),
        ],
    },
    {
        "value": "ui-ux-design",
        "label": "Thiết kế UI/UX",
        "fields": [
            _field(
                "design_type",
                "Design type",
                "select",
                ["Mobile App", "Website", "Dashboard", "Desktop Application", "Other"],
            ),
            _field("business_goal", "Business goal", "text"),
            _field("target_users", "Target users", "text"),
            _field(
                "design_scope",
                "Design scope",
                "select",
                ["New design", "Redesign", "Improve existing design", "Design system only"],
            ),
            _field(
                "expected_deliverables",
                "Expected deliverables",
                "multiselect",
                [
                    "Wireframes", "User flows", "High-fidelity UI", "Prototype",
                    "Design system", "UX research",
                ],
            ),
        ],
    },
    {
        "value": "graphic-design",
        "label": "Thiết kế đồ hoạ",
        "fields": [
            _field(
                "design_category",
                "Design category",
                "select",
                [
                    "Logo", "Brand identity", "Social media graphics", "Poster", "Brochure",
                    "Packaging", "Presentation", "Illustration", "Other",
                ],
            ),
            _field("business_goal", "Business goal", "text"),
            _field("target_users", "Target users", "text"),
            _field(
                "brand_assets_available",
                "Brand assets available",
                "select",
                ["Yes", "Partial", "None"],
            ),
            _field(
                "expected_deliverables",
                "Expected deliverables",
                "multiselect",
                [
                    "Source files", "Print-ready files", "Social media versions",
                    "Multiple revisions", "Brand guideline",
                ],
            ),
        ],
    },
    {
        "value": "digital-marketing-consulting",
        "label": "Tư vấn Digital Marketing",
        "fields": [
            _field(
                "marketing_objective",
                "Marketing objective",
                "select",
                [
                    "Brand awareness", "Lead generation", "Sales",
                    "Website traffic", "Customer retention", "Other",
                ],
            ),
            _field(
                "marketing_channels",
                "Marketing channels",
                "multiselect",
                ["Facebook", "Instagram", "TikTok", "Google", "LinkedIn", "Email", "Other"],
            ),
            _field("target_audience", "Target audience", "text"),
            _field(
                "services_required",
                "Services required",
                "multiselect",
                [
                    "Strategy", "Advertising", "SEO",
                    "Content planning", "Analytics", "Campaign management",
                ],
            ),
            _field(
                "current_marketing_status",
                "Current marketing status",
                "select",
                ["No marketing yet", "Existing campaigns", "Need optimization"],
            ),
        ],
    },
    {
        "value": "content-writer",
        "label": "Viết nội dung / Copywriter",
        "fields": [
            _field(
                "content_type",
                "Content type",
                "select",
                [
                    "Website copy", "Blog", "Product descriptions", "Email", "Advertisement",
                    "Social media", "Script", "Press release", "Other",
                ],
            ),
            _field(
                "content_objective",
                "Content objective",
                "select",
                ["Inform", "Sell", "Educate", "Promote", "Entertain"],
            ),
            _field("target_audience", "Target audience", "text"),
            _field(
                "tone_of_writing",
                "Tone of writing",
                "select",
                ["Professional", "Friendly", "Formal", "Casual", "Persuasive"],
            ),
            _field("content_volume", "Approximate content volume", "text"),
        ],
    },
    {
        "value": "photography&videography",
        "label": "Nhiếp ảnh & Quay dựng video",
        "fields": [
            _field(
                "project_type",
                "Project type",
                "select",
                [
                    "Portrait", "Wedding", "Event", "Product", "Food", "Corporate",
                    "Real estate", "Commercial video", "Social media content", "Other",
                ],
            ),
            _field(
                "purpose",
                "Purpose",
                "select",
                ["Marketing", "Personal", "Corporate", "Documentation", "Other"],
            ),
            _field(
                "location",
                "Location",
                "select",
                ["Studio", "Client location", "Outdoor", "Not decided"],
            ),
            _field(
                "required_deliverables",
                "Required deliverables",
                "multiselect",
                [
                    "Edited photos", "Raw photos", "Highlight video",
                    "Full video", "Short-form social media clips",
                ],
            ),
            _field(
                "estimated_duration",
                "Estimated duration",
                "select",
                ["Half day", "One day", "Multiple days", "Other"],
            ),
        ],
    },
]

PROFESSIONS_BY_VALUE: dict[str, ProfessionDef] = {p["value"]: p for p in PROFESSIONS}


def required_field_keys(profession: str) -> set[str]:
    profession_def = PROFESSIONS_BY_VALUE.get(profession)
    if profession_def is None:
        return set()
    return {f["field_key"] for f in profession_def["fields"] if f["is_required"]}


def all_professions() -> list[dict[str, str]]:
    """Danh sách nghề cho FE đổ dropdown: ``[{"value": slug, "label": nhãn}, ...]``."""
    return [{"value": p["value"], "label": p["label"]} for p in PROFESSIONS]


def is_valid_profession(value: str | None) -> bool:
    """Slug có nằm trong danh mục không. ``None`` = chưa chọn nghề, vẫn hợp lệ."""
    return value is None or value in PROFESSIONS_BY_VALUE


def profession_label(value: str | None) -> str | None:
    """Nhãn tiếng Việt của một slug; ``None`` nếu chưa chọn / không tồn tại."""
    if not value:
        return None
    profession_def = PROFESSIONS_BY_VALUE.get(value)
    return profession_def["label"] if profession_def else None


# Mẫu LỪA ĐẢO thường gặp theo từng nghề. Lead qualifier đọc qua `profession_scam_hint`
# để đối chiếu với lời khách rồi đưa vào `red_flags` NẾU khớp — KHÔNG phải để bịa cờ đỏ
# khi khách không có dấu hiệu. Đây là "kiến thức theo nghề" bản NHẸ, chèn thẳng vào
# prompt; phần nặng (khung đánh giá đầy đủ) do FAISS retriever lo.  #Huynh
_PROFESSION_SCAM_HINTS: dict[str, str] = {
    "software-developer": (
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
    "digital-marketing-consulting": (
        "trả theo KPI/kết quả nhưng không đặt cọc; đòi quyền admin tài khoản quảng cáo / "
        "fanpage trước khi thanh toán; hứa chia % hoa hồng thay vì trả phí"
    ),
    "content-writer": (
        "'viết thử vài bài test' không công; đòi nộp bài hoàn chỉnh trước khi chốt; gom "
        "'bài mẫu' của nhiều ứng viên thành nội dung dùng thật"
    ),
    "photography&videography": (
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
