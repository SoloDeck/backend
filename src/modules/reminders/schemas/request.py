import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ReminderRequest(BaseModel):
    target_type: str
    target_id: uuid.UUID
    reminder_type: str
    channel: str
    scheduled_at: datetime
    message_preview: str | None = None
    # Ảnh chèn vào thư (mã QR chuyển khoản, ảnh sản phẩm…). Mỗi phần tử là
    # `{"key", "filename", "content_type"}` do `POST /reminders/attachments` trả về.
    attachments: list[dict[str, str]] = Field(default_factory=list)


class ReminderRuleUpdate(BaseModel):
    """Sửa một quy tắc. Mọi trường đều tuỳ chọn — bật/tắt một công tắc không nên bắt
    frontend gửi lại nguyên cả quy tắc."""

    is_enabled: bool | None = None
    offset_days: int | None = None
    repeat_every_days: int | None = None
    channel: str | None = None
    auto_send: bool | None = None
    send_at_hour: int | None = None
    # Nội dung mẫu tự soạn. Gửi chuỗi rỗng để trả lời nhắc về template mặc định.
    message_template: str | None = None
