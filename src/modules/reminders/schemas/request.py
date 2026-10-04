import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from src.modules.reminders.domain.entities.reminder import ReminderType
from src.modules.reminders.domain.value_objects.reminder_target import ReminderTargetType

# Matches the notification_channel Postgres enum (also used by UserModel) — no
# existing Python StrEnum for it, and a bare `str` here let an invalid value (e.g.
# "sms") pass pydantic validation and crash with a raw asyncpg
# InvalidTextRepresentationError at the DB layer instead of a clean 422, the same
# class of bug fixed for query-filter params on fix/critical-api-bugs.
NotificationChannel = Literal["email", "in_app", "both", "zalo"]


def _must_be_future(v: datetime) -> datetime:
    # Treat a timezone-naive value as UTC (matches datetime.now(UTC) used everywhere
    # else in this codebase) rather than comparing against the server's local clock,
    # which would make this check's outcome depend on the deploy environment's TZ.
    compare = v if v.tzinfo is not None else v.replace(tzinfo=UTC)
    if compare <= datetime.now(UTC):
        raise ValueError("scheduled_at must be in the future")
    return v


class CreateReminderRequest(BaseModel):
    target_type: ReminderTargetType
    target_id: uuid.UUID
    reminder_type: ReminderType
    channel: NotificationChannel
    scheduled_at: datetime
    message_preview: str | None = None
    # Ảnh chèn vào thư (mã QR chuyển khoản, ảnh sản phẩm…). Mỗi phần tử là
    # `{"key", "filename", "content_type"}` do `POST /reminders/attachments` trả về.
    attachments: list[dict[str, str]] = Field(default_factory=list)

    @field_validator("scheduled_at")
    @classmethod
    def scheduled_at_must_be_future(cls, v: datetime) -> datetime:
        return _must_be_future(v)


class UpdateReminderRequest(BaseModel):
    """target_type/target_id/reminder_type deliberately NOT accepted here
    — a reminder isn't meant to be re-pointed at a different target or type via
    update, only rescheduled/re-messaged/re-channeled. Previously this reused the
    full create schema, so every field was required (PATCH with anything less than
    the complete object 422'd) and update() unconditionally overwrote all of them,
    including target_type/target_id, with no None-guard at all.

    `attachments` THÌ NHẬN: web vẫn gửi ảnh lên khi sửa, còn pydantic lặng lẽ vứt trường lạ
    — sửa lời nhắc xong là mất ảnh QR chuyển khoản mà màn hình vẫn báo "Đã cập nhật".
    `reminder_type` vẫn không nhận: nó nằm trong khoá chống trùng của bộ tự sinh lời nhắc,
    đổi loại là lượt quét sau đẻ lại đúng lời nhắc vừa bị đổi.

    Không kiểm "phải ở tương lai" ở đây như bản Create: schema không biết giờ hẹn hiện tại.
    Lời nhắc do quy tắc tự sinh nằm chờ duyệt quá giờ hẹn thì sửa nội dung cũng bị chặn
    theo. Việc kiểm dời sang service, chỉ áp khi giờ hẹn THẬT SỰ đổi.  #Huynh"""

    scheduled_at: datetime | None = None
    message_preview: str | None = None
    channel: NotificationChannel | None = None
    attachments: list[dict[str, str]] | None = None


class ReminderRuleUpdate(BaseModel):
    """Sửa một quy tắc. Mọi trường đều tuỳ chọn — bật/tắt một công tắc không nên bắt
    frontend gửi lại nguyên cả quy tắc."""

    is_enabled: bool | None = None
    offset_days: int | None = None
    repeat_every_days: int | None = None
    channel: NotificationChannel | None = None
    # Đã bỏ: server bỏ qua giá trị này (client cũ gửi lên cũng không lỗi).
    auto_send: bool | None = None
    send_at_hour: int | None = None
    # Nội dung mẫu tự soạn. Gửi chuỗi rỗng để trả lời nhắc về template mặc định.
    message_template: str | None = None
