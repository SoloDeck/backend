"""Năm quy tắc nhắc tự động và giá trị mặc định của chúng.

Tách khỏi service để cả service, test và seeder cùng đọc MỘT nguồn. Trước đây danh mục
kiểu này hay bị chép ra hai chỗ rồi lệch nhau lúc nào không hay.  #Huynh
"""

from dataclasses import dataclass
from enum import StrEnum


class RuleType(StrEnum):
    """Năm quy tắc — đều là giá trị có sẵn trong enum `reminder_type_enum` của Postgres.

    Thứ tự khai báo = thứ tự vòng đời deal (báo giá → hợp đồng → thanh toán → giữ chân),
    và màn cài đặt hiển thị theo đúng thứ tự này. Đọc xuôi theo việc thật đang diễn ra thì
    dễ hiểu hơn xếp theo bảng chữ cái.

    `follow_up` và `custom` cố ý KHÔNG có mặt: chúng dành cho lời nhắc người dùng tự đặt,
    không có mốc thời gian nào trong dữ liệu để máy tự suy ra.
    """

    PROPOSAL_FOLLOW_UP = "proposal_follow_up"
    CONTRACT_SIGNING_NUDGE = "contract_signing_nudge"
    PAYMENT_DUE = "payment_due"
    PAYMENT_OVERDUE = "payment_overdue"
    RE_ENGAGEMENT = "re_engagement"


# Nhãn tiếng Việt cho từng biến động (placeholder) chèn được vào lời nhắc. Đặt ở BACKEND
# làm nguồn duy nhất để màn cài đặt và bộ máy soạn tin không mô tả biến theo hai kiểu khác
# nhau. Cú pháp trong template là `{ten_bien}` — bộ máy thay chuỗi khi soạn tin thật.
VARIABLE_LABELS: dict[str, str] = {
    "client_name": "Tên khách hàng",
    "deal_title": "Tên dự án",
    "invoice_number": "Số hoá đơn",
    "due_date": "Ngày tới hạn",
    "amount": "Số tiền còn lại",
    "days_late": "Số ngày quá hạn",
}


@dataclass(frozen=True)
class RuleDefault:
    offset_days: int
    repeat_every_days: int | None
    is_enabled: bool
    label: str
    """Câu mô tả cho giao diện — để backend và frontend nói cùng một thứ tiếng."""
    default_template: str
    """Nội dung mẫu mặc định. Dùng khi freelancer chưa tự soạn (message_template = NULL)."""
    variables: tuple[str, ...]
    """Các biến `{...}` template này hỗ trợ — để giao diện gợi ý cho freelancer."""


# Template mặc định — ĐÚNG câu chữ bộ máy vẫn gửi trước đây, chỉ thay phần động bằng
# placeholder `{...}` để freelancer sửa được mà vẫn giữ dữ liệu thật khi soạn tin.
_TPL_PROPOSAL_FOLLOW_UP = (
    "Chào anh/chị {client_name},\n\n"
    'Em có gửi báo giá cho dự án "{deal_title}" ít hôm trước. '
    "Không biết anh/chị đã có dịp xem qua chưa ạ?\n\n"
    "Nếu có chỗ nào cần điều chỉnh, anh/chị cứ trao đổi với em nhé.\n\n"
    "Em cảm ơn anh/chị."
)
_TPL_CONTRACT_SIGNING_NUDGE = (
    "Chào anh/chị {client_name},\n\n"
    'Hợp đồng dự án "{deal_title}" vẫn đang chờ chữ ký của anh/chị. '
    "Anh/chị xem và ký giúp em khi thuận tiện để bên em bắt đầu triển khai ạ.\n\n"
    "Em cảm ơn anh/chị."
)
_TPL_PAYMENT_DUE = (
    "Chào anh/chị {client_name},\n\n"
    "Em xin nhắc anh/chị hoá đơn {invoice_number} sẽ tới hạn vào ngày {due_date}, "
    "số tiền còn lại {amount}.\n\n"
    "Anh/chị sắp xếp giúp em nhé. Em cảm ơn anh/chị."
)
_TPL_PAYMENT_OVERDUE = (
    "Chào anh/chị {client_name},\n\n"
    "Hoá đơn {invoice_number} đã quá hạn {days_late} ngày (hạn ngày {due_date}), "
    "số tiền còn lại {amount}.\n\n"
    "Anh/chị kiểm tra giúp em nhé. Nếu đã thanh toán rồi thì anh/chị bỏ qua email này "
    "giúp em ạ.\n\n"
    "Em cảm ơn anh/chị."
)
_TPL_RE_ENGAGEMENT = (
    "Chào anh/chị {client_name},\n\n"
    "Lâu rồi mình chưa có dịp trao đổi, em viết vài dòng hỏi thăm anh/chị ạ.\n\n"
    "Nếu sắp tới anh/chị có dự án nào cần hỗ trợ, anh/chị cứ nhắn em nhé.\n\n"
    "Em cảm ơn anh/chị."
)


RULE_DEFAULTS: dict[RuleType, RuleDefault] = {
    RuleType.PROPOSAL_FOLLOW_UP: RuleDefault(
        offset_days=3,
        repeat_every_days=None,
        is_enabled=True,
        label="Hỏi thăm khi khách chưa phản hồi báo giá",
        default_template=_TPL_PROPOSAL_FOLLOW_UP,
        variables=("client_name", "deal_title"),
    ),
    RuleType.CONTRACT_SIGNING_NUDGE: RuleDefault(
        offset_days=2,
        repeat_every_days=None,
        is_enabled=True,
        label="Nhắc khách ký hợp đồng còn chờ",
        default_template=_TPL_CONTRACT_SIGNING_NUDGE,
        variables=("client_name", "deal_title"),
    ),
    RuleType.PAYMENT_DUE: RuleDefault(
        offset_days=3,
        repeat_every_days=None,
        is_enabled=True,
        label="Nhắc khách trước khi hoá đơn tới hạn",
        default_template=_TPL_PAYMENT_DUE,
        variables=("client_name", "invoice_number", "due_date", "amount"),
    ),
    RuleType.PAYMENT_OVERDUE: RuleDefault(
        offset_days=1,
        repeat_every_days=7,
        is_enabled=True,
        label="Nhắc lại khi hoá đơn đã quá hạn",
        default_template=_TPL_PAYMENT_OVERDUE,
        variables=("client_name", "invoice_number", "days_late", "due_date", "amount"),
    ),
    # Quy tắc DUY NHẤT chạm tới khách không có việc gì đang làm dở. Bật nhầm là email hàng
    # loạt tới toàn bộ khách cũ, nên mặc định TẮT — người dùng phải chủ động bật.  #Huynh
    RuleType.RE_ENGAGEMENT: RuleDefault(
        offset_days=60,
        repeat_every_days=60,
        is_enabled=False,
        label="Chăm sóc lại khách đã lâu không liên lạc",
        default_template=_TPL_RE_ENGAGEMENT,
        variables=("client_name",),
    ),
}

# Chỉ hai quy tắc này có ý nghĩa khi lặp lại. Nhắc mãi một báo giá khách đã lờ đi thì
# không phải chăm sóc, mà là làm phiền.
REPEATABLE_RULES = frozenset({RuleType.PAYMENT_OVERDUE, RuleType.RE_ENGAGEMENT})

# Giới hạn độ dài template freelancer tự soạn — đủ cho một email lịch sự, chặn nội dung
# khổng lồ làm nặng bảng và email.
MAX_TEMPLATE_LENGTH = 2000


def effective_template(rule_type: RuleType, message_template: str | None) -> str:
    """Template đang có hiệu lực: bản freelancer tự soạn, hoặc mặc định nếu bỏ trống."""
    custom = (message_template or "").strip()
    return custom or RULE_DEFAULTS[rule_type].default_template


def render_reminder_template(template: str, variables: dict[str, str]) -> str:
    """Thay các placeholder `{ten_bien}` bằng giá trị thật.

    Dùng thay chuỗi tường minh thay vì `str.format` để một dấu `{` lạc trong nội dung
    freelancer gõ không làm cả lượt quét đổ vỡ.
    """
    result = template
    for name, value in variables.items():
        result = result.replace("{" + name + "}", str(value))
    return result
