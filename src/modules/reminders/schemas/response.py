import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ReminderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_user_id: uuid.UUID
    target_type: str
    target_id: uuid.UUID
    reminder_type: str
    channel: str
    status: str
    scheduled_at: datetime
    message_preview: str | None
    # Để giao diện phân biệt "tôi tự đặt" với "hệ thống tự sinh, đang chờ tôi duyệt" —
    # người dùng cần biết trước khi bấm gửi một tin nhắn tới khách hàng thật.
    requires_approval: bool = False
    created_by_rule: bool = False
    created_at: datetime
    updated_at: datetime


class ReminderRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rule_type: str
    is_enabled: bool
    offset_days: int
    repeat_every_days: int | None
    channel: str
    auto_send: bool
    send_at_hour: int
    # Câu mô tả lấy từ danh mục ở backend thay vì để frontend tự chế — hai nơi viết hai
    # kiểu thì người dùng đọc tài liệu và đọc màn hình sẽ thấy khác nhau.
    label: str = ""
    supports_repeat: bool = False


class ReminderDeliveryResponse(BaseModel):
    """Kết quả bấm "Gửi ngay".

    Trả kèm `detail` — một câu tiếng Việt hiện thẳng lên toast — thay vì bắt frontend tự
    đoán nghĩa của `status`. Lý do hỏng ("khách chưa có email") chỉ backend mới biết.
    """

    reminder: ReminderResponse
    status: str
    detail: str
    delivered: bool
