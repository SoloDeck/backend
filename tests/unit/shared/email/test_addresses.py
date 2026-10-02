"""Chặn sớm email khách chắc chắn không gửi được."""

import pytest

from src.shared.email.addresses import looks_like_email


@pytest.mark.parametrize(
    "value",
    [
        "khach@example.com",
        "  khach@example.com  ",
        "ten.ho+tag@sub.example.co.uk",
        "huynhhqse173269@fpt.edu.vn",
        "khach-e2e@example.test",
        "a_b-c@xn--p1ai.xn--p1ai",
    ],
)
def test_dia_chi_hop_le(value: str) -> None:
    assert looks_like_email(value)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
        "khong-co-a-cong",
        "a@b",
        "@example.com",
        "khach@",
        "khach@example..com",
        "khach@-example.com",
        "a@x.com, b@y.com",
        "a@x.com;b@y.com",
        "Tên Khách <khach@example.com>",
        "<khach@example.com>",
        "khách@example.com",
        "khach@example.com\r\nBcc: x@y.com",
        "khach @example.com",
    ],
)
def test_dia_chi_chac_chan_khong_gui_duoc(value: str) -> None:
    assert not looks_like_email(value)
