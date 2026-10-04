"""Nhận ra số tiền gõ tay trong lời nhắn gửi khách.

Bộ ví dụ ở đây được SAO Y sang test của web (`invoiceComposer.test.ts`): hai bản cài đặt
(Python và TypeScript) phải cho cùng kết quả, không thì web báo ổn mà backend chặn.  #Huynh
"""

import pytest

from src.modules.invoices.domain.typed_amounts import find_money_amounts, mismatched_amounts

LA_TIEN = [
    ("Tổng số tiền cần thanh toán là 511.900.000 ₫.", [511_900_000]),
    ("Phí 500k", [500_000]),
    ("Tạm ứng 30tr", [30_000_000]),
    ("Khoảng 1,5 triệu", [1_500_000]),
    ("Dự án 2 tỷ", [2_000_000_000]),
    ("Chỉ 50.000đ", [50_000]),
    ("Chỉ 50.000 đồng", [50_000]),
    ("Giá 1,500", [1_500]),
    ("VND: 15.000.000 VND", [15_000_000]),
    ("Đợt 1 là 100.000.000 ₫, đợt 2 là 421.900.000 ₫", [100_000_000, 421_900_000]),
    ("500K và 30TR", [500_000, 30_000_000]),
]

KHONG_PHAI_TIEN = [
    "Gọi 0352015349 nhé",
    "Hạn thanh toán 16/10/2026",
    "Hạn 16.10.2026",
    "Thanh toán đợt 2",
    "Tạm ứng 50%",
    "Mã INV-20261003-AB12",
    "Tối đa 2 vòng chỉnh sửa",
    "Giao 5km",
    "Dài 5 trang",
    "Phiên bản 3.5",
    "Số tài khoản 0123456789",
    "Tổng số tiền cần thanh toán là {{tong_tien}}.",
    "",
]


@pytest.mark.parametrize(("text", "expected"), LA_TIEN)
def test_nhan_ra_so_tien(text: str, expected: list[int]) -> None:
    assert find_money_amounts(text) == expected


@pytest.mark.parametrize("text", KHONG_PHAI_TIEN)
def test_so_tran_khong_bi_coi_la_tien(text: str) -> None:
    assert find_money_amounts(text) == []


def test_none_khong_no() -> None:
    assert find_money_amounts(None) == []


class TestMismatchedAmounts:
    def test_so_khop_hoa_don_thi_cho_qua(self) -> None:
        text = "Tạm tính 100.000.000 ₫, thuế 8.000.000 ₫, tổng 108.000.000 ₫."
        assert mismatched_amounts(text, [100_000_000, 8_000_000, 108_000_000]) == []

    def test_so_la_thi_bi_nêu_ra(self) -> None:
        text = "Hóa đơn 521.900.000 ₫ và phụ thu 1.000.000 ₫."
        assert mismatched_amounts(text, [521_900_000]) == [1_000_000]

    def test_le_mot_dong_do_lam_tron_van_cho_qua(self) -> None:
        assert mismatched_amounts("Tổng 1.080.001 ₫", [1_080_000]) == []
        assert mismatched_amounts("Tổng 1.080.003 ₫", [1_080_000]) == [1_080_003]
