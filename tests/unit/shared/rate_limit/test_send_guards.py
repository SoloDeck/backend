"""Chống bấm/bắn dồn dập làm cạn hạn mức gửi thư dùng chung của hệ thống."""

import uuid

import pytest

from src.shared.exceptions.domain import RateLimitError
from src.shared.rate_limit import send_guards
from src.shared.rate_limit.auth_guards import reset_moi_bo_dem


@pytest.fixture(autouse=True)
def _sach_bo_dem():  # type: ignore[no-untyped-def]
    reset_moi_bo_dem()
    yield
    reset_moi_bo_dem()


def test_hai_muoi_luot_dau_di_qua_luot_thu_hai_muoi_mot_bi_chan() -> None:
    user = uuid.uuid4()
    for _ in range(20):
        send_guards.chan_nhip_gui_giay_to(user)
    with pytest.raises(RateLimitError) as bat:
        send_guards.chan_nhip_gui_giay_to(user)
    assert "gửi" in bat.value.message


def test_moi_nguoi_dung_co_bo_dem_rieng() -> None:
    nguoi_a, nguoi_b = uuid.uuid4(), uuid.uuid4()
    for _ in range(20):
        send_guards.chan_nhip_gui_giay_to(nguoi_a)
    # A đã hết lượt nhưng B không bị vạ lây.
    send_guards.chan_nhip_gui_giay_to(nguoi_b)


def test_reset_moi_bo_dem_cung_xoa_bo_dem_gui_giay_to() -> None:
    """Conftest chỉ gọi `reset_moi_bo_dem`; nếu nó không dọn bộ đếm này thì các bài test cộng dồn
    lượt của nhau và đỏ tuỳ thứ tự chạy."""
    user = uuid.uuid4()
    for _ in range(20):
        send_guards.chan_nhip_gui_giay_to(user)
    reset_moi_bo_dem()
    send_guards.chan_nhip_gui_giay_to(user)  # không ném
