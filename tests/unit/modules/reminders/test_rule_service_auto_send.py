"""Công tắc "tự gửi" của quy tắc nhắc đã bỏ: lời nhắc do quy tắc tạo luôn chờ người duyệt.

Service vẫn NHẬN tham số `auto_send` (client cũ còn gửi trường này lên) nhưng không được ghi nó —
ghi vào là mở lại đường cho email bay tới khách mà chưa qua tay người dùng.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from src.modules.reminders.application.rule_service import ReminderRulesService


def a_service(rule: SimpleNamespace) -> ReminderRulesService:
    db = MagicMock()
    db.scalar = AsyncMock(return_value=rule)
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    service = ReminderRulesService(db=db)
    service.list_for_user = AsyncMock(return_value=[rule])  # type: ignore[method-assign]
    return service


def a_rule(**over) -> SimpleNamespace:  # type: ignore[no-untyped-def]
    values = {
        "rule_type": "payment_due",
        "is_enabled": True,
        "offset_days": 3,
        "repeat_every_days": None,
        "channel": "email",
        "auto_send": False,
        "send_at_hour": 9,
        "message_template": None,
    }
    values.update(over)
    return SimpleNamespace(**values)


async def test_gui_auto_send_bat_len_thi_khong_ghi_nhung_cac_truong_khac_van_luu() -> None:
    rule = a_rule()

    updated = await a_service(rule).update(
        uuid.uuid4(), "payment_due", auto_send=True, offset_days=5, send_at_hour=14
    )

    assert updated.auto_send is False
    assert (updated.offset_days, updated.send_at_hour) == (5, 14)

