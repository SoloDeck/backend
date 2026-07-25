"""Bảo trì vòng đời gói: báo trước sắp hết kỳ, tự hạ Free khi hết kỳ.

Đây là logic ĐỘNG TỚI QUYỀN của người dùng (mất tính năng AI khi bị hạ gói), nên kiểm kỹ:
chỉ báo đúng ngày ngưỡng, và chỉ hạ đúng gói đã quá hạn.
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


def _db(rows: list, free_plan=None) -> AsyncMock:
    db = AsyncMock()
    result = MagicMock()
    result.all.return_value = rows
    db.execute = AsyncMock(return_value=result)
    db.scalar = AsyncMock(return_value=free_plan)  # dùng cho tra gói free lúc hạ
    return db


class TestWarnExpiring:
    async def test_bao_truoc_dung_ngay_nguong(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        sent = AsyncMock()
        monkeypatch.setattr(mod, "send_email", sent)
        row = _row(NOW + timedelta(days=EXPIRY_WARN_DAYS))
        svc = SubscriptionLifecycleService(db=_db([row]), now=NOW)

        counts = await svc.run_daily_maintenance()

        assert counts["expiry_warned"] == 1
        assert counts["downgraded"] == 0
        sent.assert_awaited_once()

    async def test_khong_bao_khi_con_xa_han(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        sent = AsyncMock()
        monkeypatch.setattr(mod, "send_email", sent)
        row = _row(NOW + timedelta(days=EXPIRY_WARN_DAYS + 5))
        svc = SubscriptionLifecycleService(db=_db([row]), now=NOW)

        counts = await svc.run_daily_maintenance()

        assert counts["expiry_warned"] == 0
        sent.assert_not_awaited()


class TestDowngradeExpired:
    async def test_ha_ve_free_va_gui_email(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        sent = AsyncMock()
        monkeypatch.setattr(mod, "send_email", sent)
        row = _row(NOW - timedelta(days=1))
        free_plan = SimpleNamespace(id=uuid.uuid4(), slug="free", name="Free")
        svc = SubscriptionLifecycleService(db=_db([row], free_plan=free_plan), now=NOW)

        counts = await svc.run_daily_maintenance()

        assert counts["downgraded"] == 1
        sub, _, _ = row
        assert sub.plan_id == free_plan.id  # đã đổi sang gói free
        assert sub.current_period_end > NOW  # kỳ mới được đẩy dài ra
        sent.assert_awaited()

    async def test_thieu_goi_free_thi_khong_ha(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        sent = AsyncMock()
        monkeypatch.setattr(mod, "send_email", sent)
        row = _row(NOW - timedelta(days=1))
        original_plan_id = row[0].plan_id
        svc = SubscriptionLifecycleService(db=_db([row], free_plan=None), now=NOW)

        counts = await svc.run_daily_maintenance()

        assert counts["downgraded"] == 0
        assert row[0].plan_id == original_plan_id  # không đụng gì khi thiếu gói free
