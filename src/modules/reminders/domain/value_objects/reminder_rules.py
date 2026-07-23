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


@dataclass(frozen=True)
class RuleDefault:
    offset_days: int
    repeat_every_days: int | None
    is_enabled: bool
    label: str
    """Câu mô tả cho giao diện — để backend và frontend nói cùng một thứ tiếng."""


RULE_DEFAULTS: dict[RuleType, RuleDefault] = {
    RuleType.PROPOSAL_FOLLOW_UP: RuleDefault(
        offset_days=3,
        repeat_every_days=None,
        is_enabled=True,
        label="Hỏi thăm khi khách chưa phản hồi báo giá",
    ),
    RuleType.CONTRACT_SIGNING_NUDGE: RuleDefault(
        offset_days=2,
        repeat_every_days=None,
        is_enabled=True,
        label="Nhắc khách ký hợp đồng còn chờ",
    ),
    RuleType.PAYMENT_DUE: RuleDefault(
        offset_days=3,
        repeat_every_days=None,
        is_enabled=True,
        label="Nhắc khách trước khi hoá đơn tới hạn",
    ),
    RuleType.PAYMENT_OVERDUE: RuleDefault(
        offset_days=1,
        repeat_every_days=7,
        is_enabled=True,
        label="Nhắc lại khi hoá đơn đã quá hạn",
    ),
    # Quy tắc DUY NHẤT chạm tới khách không có việc gì đang làm dở. Bật nhầm là email hàng
    # loạt tới toàn bộ khách cũ, nên mặc định TẮT — người dùng phải chủ động bật.  #Huynh
    RuleType.RE_ENGAGEMENT: RuleDefault(
        offset_days=60,
        repeat_every_days=60,
        is_enabled=False,
        label="Chăm sóc lại khách đã lâu không liên lạc",
    ),
}

# Chỉ hai quy tắc này có ý nghĩa khi lặp lại. Nhắc mãi một báo giá khách đã lờ đi thì
# không phải chăm sóc, mà là làm phiền.
REPEATABLE_RULES = frozenset({RuleType.PAYMENT_OVERDUE, RuleType.RE_ENGAGEMENT})
