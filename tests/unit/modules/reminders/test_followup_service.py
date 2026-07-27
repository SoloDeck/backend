"""FollowUpService nạp ngữ cảnh THẬT từ DB — không để AI tự bịa số liệu."""

import uuid
from unittest.mock import AsyncMock

import pytest

from src.modules.reminders.application.followup_service import FollowUpService
from src.shared.exceptions.domain import ValidationError


class TestMoneyFormat:
    def test_dinh_dang_tien_truoc_khi_dua_cho_ai(self) -> None:
        """Đưa "700000 VND" thì AI chép nguyên xi vào tin nhắn gửi khách — cẩu thả."""
        assert FollowUpService._money(700000, "VND") == "700.000 ₫"
        assert FollowUpService._money(20000000, "VND") == "20.000.000 ₫"

    def test_khong_co_tien_thi_de_trong_chu_khong_bia_0(self) -> None:
        assert FollowUpService._money(None, "VND") is None

    def test_tien_te_khac_van_dinh_dang_duoc(self) -> None:
        assert FollowUpService._money(1500, "USD") == "1.500 USD"


class TestTargetType:
    async def test_target_type_la_thi_bao_loi_ro_rang(self) -> None:
        service = FollowUpService(db=AsyncMock())

        with pytest.raises(ValidationError, match="target_type"):
            await service.generate(
                uuid.uuid4(),
                reminder_type="follow_up",
                target_type="khong_ton_tai",
                target_id=uuid.uuid4(),
                ai_facade=AsyncMock(),
            )
