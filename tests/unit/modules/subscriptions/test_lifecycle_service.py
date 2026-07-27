"""Cảnh báo email sắp hết kỳ (SubscriptionLifecycleService).

Service này CHỈ gửi email báo trước — KHÔNG hạ gói (việc hạ Free do
`SubscriptionsService.expire_lapsed_subscriptions` lo). Kiểm: chỉ báo đúng ngày ngưỡng.
"""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from src.modules.subscriptions.application import lifecycle_service as mod
from src.modules.subscriptions.application.lifecycle_service import (
    EXPIRY_WARN_DAYS,
    SubscriptionLifecycleService,
)

NOW = datetime(2026, 7, 25, tzinfo=UTC)


def _row(
    period_end: datetime,
    *,
    slug: str = "pro",
    plan_name: str = "Pro",
    email: str = "a@b.com",
):
    plan_id = uuid.uuid4()
    sub = SimpleNamespace(
        id=uuid.uuid4(),
        plan_id=plan_id,
        status="active",
        current_period_start=period_end - timedelta(days=30),
        current_period_end=period_end,
    )
    plan = SimpleNamespace(id=plan_id, slug=slug, name=plan_name)
    user = SimpleNamespace(id=uuid.uuid4(), email=email, full_name="A", deleted_at=None)
    return (sub, plan, user)


def _db(rows: list) -> AsyncMock:
    db = AsyncMock()
    result = MagicMock()
    result.all.return_value = rows
    db.execute = AsyncMock(return_value=result)
    return db


class TestWarnExpiring:
    async def test_bao_truoc_dung_ngay_nguong(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        sent = AsyncMock()
        monkeypatch.setattr(mod, "send_email", sent)
        row = _row(NOW + timedelta(days=EXPIRY_WARN_DAYS))
        svc = SubscriptionLifecycleService(db=_db([row]), now=NOW)

        counts = await svc.run_daily_maintenance()

        assert counts["expiry_warned"] == 1
        sent.assert_awaited_once()

    async def test_khong_bao_khi_con_xa_han(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        sent = AsyncMock()
        monkeypatch.setattr(mod, "send_email", sent)
        row = _row(NOW + timedelta(days=EXPIRY_WARN_DAYS + 5))
        svc = SubscriptionLifecycleService(db=_db([row]), now=NOW)

        counts = await svc.run_daily_maintenance()

        assert counts["expiry_warned"] == 0
        sent.assert_not_awaited()

    async def test_bo_qua_khi_da_qua_han(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        """Đã quá hạn (âm ngày) không phải việc của service này — module subscriptions lo hạ gói."""
        sent = AsyncMock()
        monkeypatch.setattr(mod, "send_email", sent)
        row = _row(NOW - timedelta(days=1))
        svc = SubscriptionLifecycleService(db=_db([row]), now=NOW)

        counts = await svc.run_daily_maintenance()

        assert counts["expiry_warned"] == 0
        sent.assert_not_awaited()
