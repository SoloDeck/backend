"""Cổng AI: chặn đúng, đếm đúng. Đây là logic tính tiền — sai là mất tiền thật."""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.modules.subscriptions.application.ai_usage import AiUsageService
from src.shared.exceptions.domain import EntitlementError, RateLimitError

NOW = datetime.now(UTC)


def _sub():
    return SimpleNamespace(
        id=uuid.uuid4(),
        plan_id=uuid.uuid4(),
        current_period_start=NOW - timedelta(days=5),
        current_period_end=NOW + timedelta(days=25),
    )


def _plan(*, can_use_ai: bool, limit: int):
    return SimpleNamespace(can_use_ai=can_use_ai, max_ai_generations_per_month=limit)


def _record(used: int):
    return SimpleNamespace(
        ai_generations_used=used,
        billing_period_end=NOW + timedelta(days=25),
    )


def _service(*rows) -> AiUsageService:
    db = AsyncMock()
    db.scalar.side_effect = list(rows)
    # db.add() là hàm ĐỒNG BỘ của SQLAlchemy — để AsyncMock thì nó trả về coroutine
    # không ai await, pytest báo lỗi.
    db.add = MagicMock()
    return db_service(db)


def db_service(db) -> AiUsageService:
    return AiUsageService(db=db)


class TestConsume:
    async def test_khong_co_goi_thi_chan(self) -> None:
        with pytest.raises(EntitlementError):
            await _service(None).consume(uuid.uuid4())

    async def test_goi_free_khong_co_ai_thi_chan(self) -> None:
        """Trước đây `user_can_use_ai=True` bị HARDCODE — gói free dùng AI miễn phí."""
        service = _service(_sub(), _plan(can_use_ai=False, limit=0))

        with pytest.raises(EntitlementError):
            await service.consume(uuid.uuid4())

    async def test_het_han_muc_thang_thi_chan(self) -> None:
        """Gói Pro 50 lượt/tháng. Trước đây KHÔNG AI ĐẾM — gọi vô hạn."""
        service = _service(_sub(), _plan(can_use_ai=True, limit=50), _record(used=50))

        with pytest.raises(RateLimitError):
            await service.consume(uuid.uuid4())

    async def test_con_han_muc_thi_cho_qua_va_dem_them_mot(self) -> None:
        record = _record(used=49)
        service = _service(_sub(), _plan(can_use_ai=True, limit=50), record)

        await service.consume(uuid.uuid4())

        assert record.ai_generations_used == 50

    async def test_chua_co_ban_ghi_thi_tao_moi(self) -> None:
        db = AsyncMock()
        db.scalar.side_effect = [_sub(), _plan(can_use_ai=True, limit=50), None]
        db.add = MagicMock()
        service = AiUsageService(db=db)

        await service.consume(uuid.uuid4())

        db.add.assert_called_once()
        created = db.add.call_args[0][0]
        assert created.ai_generations_used == 1


class TestQuotaWarning:
    """Email "sắp hết lượt AI" gửi ĐÚNG một lần khi vượt ngưỡng (không cần cột cờ)."""

    def _user(self):  # type: ignore[no-untyped-def]
        return SimpleNamespace(id=uuid.uuid4(), email="a@b.com", full_name="Chị Lan")

    async def test_gui_khi_dung_dat_nguong(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        import src.shared.email.smtp as smtp_mod

        sent = AsyncMock()
        monkeypatch.setattr(smtp_mod, "send_email", sent)
        db = AsyncMock()
        db.scalar = AsyncMock(return_value=self._user())
        service = AiUsageService(db=db)

        # limit 50 -> ngưỡng ceil(50*0.8) = 40.
        await service._maybe_warn_quota(uuid.uuid4(), _record(used=40), 50)

        sent.assert_awaited_once()

    async def test_khong_gui_khi_chua_toi_nguong(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        import src.shared.email.smtp as smtp_mod

        sent = AsyncMock()
        monkeypatch.setattr(smtp_mod, "send_email", sent)
        service = AiUsageService(db=AsyncMock())

        await service._maybe_warn_quota(uuid.uuid4(), _record(used=39), 50)

        sent.assert_not_awaited()

    async def test_chi_gui_dung_lan_vuot_nguong(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        """41 đã qua ngưỡng 40 -> KHÔNG gửi lại (chỉ đúng lần == ngưỡng mới gửi)."""
        import src.shared.email.smtp as smtp_mod

        sent = AsyncMock()
        monkeypatch.setattr(smtp_mod, "send_email", sent)
        service = AiUsageService(db=AsyncMock())

        await service._maybe_warn_quota(uuid.uuid4(), _record(used=41), 50)

        sent.assert_not_awaited()

    async def test_limit_0_khong_gui(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        import src.shared.email.smtp as smtp_mod

        sent = AsyncMock()
        monkeypatch.setattr(smtp_mod, "send_email", sent)
        service = AiUsageService(db=AsyncMock())

        await service._maybe_warn_quota(uuid.uuid4(), _record(used=0), 0)

        sent.assert_not_awaited()


class TestSummary:
    async def test_bao_cao_dung_so_luot_con_lai(self) -> None:
        service = _service(_sub(), _plan(can_use_ai=True, limit=50), _record(used=12))

        result = await service.summary(uuid.uuid4())

        assert result["used"] == 12
        assert result["limit"] == 50
        assert result["remaining"] == 38
        assert result["can_use_ai"] is True

    async def test_khong_co_goi_thi_bao_0(self) -> None:
        result = await _service(None).summary(uuid.uuid4())

        assert result == {"used": 0, "limit": 0, "remaining": 0, "can_use_ai": False}
