"""Đọc số tiền đồng thành chữ — phần "bằng chữ" trong hợp đồng.

Bản trước để AI tự viết phần chữ và model đọc sai số tiền được, nên giờ làm bằng code. Các ca dưới
đây là những chỗ tiếng Việt hay trượt: "mười/mươi", "mốt", "lăm", "linh", và hàng trăm bằng 0 chỉ
đọc khi đứng sau một nhóm lớn hơn.
"""

import pytest

from src.shared.domain.vn_number import number_in_words, vnd_in_words


class TestNumberInWords:
    @pytest.mark.parametrize("value", [0, -1, -12_000_000])
    def test_khong_va_am_ra_rong(self, value: int) -> None:
        assert number_in_words(value) == ""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (1, "một"),
            (5, "năm"),
            (9, "chín"),
            (10, "mười"),
            (11, "mười một"),
            (15, "mười lăm"),
            (19, "mười chín"),
            (20, "hai mươi"),
            (21, "hai mươi mốt"),
            (24, "hai mươi bốn"),
            (25, "hai mươi lăm"),
            (55, "năm mươi lăm"),
            (99, "chín mươi chín"),
        ],
    )
    def test_duoi_100(self, value: int, expected: str) -> None:
        assert number_in_words(value) == expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (100, "một trăm"),
            (101, "một trăm linh một"),
            (105, "một trăm linh năm"),
            (110, "một trăm mười"),
            (115, "một trăm mười lăm"),
            (200, "hai trăm"),
            (999, "chín trăm chín mươi chín"),
        ],
    )
    def test_hang_tram(self, value: int, expected: str) -> None:
        assert number_in_words(value) == expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (1_000, "một nghìn"),
            (1_005, "một nghìn không trăm linh năm"),
            (1_050, "một nghìn không trăm năm mươi"),
            (1_500, "một nghìn năm trăm"),
            (12_000, "mười hai nghìn"),
            (21_000, "hai mươi mốt nghìn"),
            (999_999, "chín trăm chín mươi chín nghìn chín trăm chín mươi chín"),
        ],
    )
    def test_hang_nghin(self, value: int, expected: str) -> None:
        assert number_in_words(value) == expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (1_000_000, "một triệu"),
            (3_600_000, "ba triệu sáu trăm nghìn"),
            (1_615_000, "một triệu sáu trăm mười lăm nghìn"),
            (12_000_000, "mười hai triệu"),
            (3_005_000, "ba triệu không trăm linh năm nghìn"),
            (1_000_001, "một triệu không trăm linh một"),
            (1_001_000, "một triệu không trăm linh một nghìn"),
            (999_000_000, "chín trăm chín mươi chín triệu"),
        ],
    )
    def test_hang_trieu(self, value: int, expected: str) -> None:
        assert number_in_words(value) == expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (1_000_000_000, "một tỷ"),
            (2_500_000_000, "hai tỷ năm trăm triệu"),
            (1_000_000_001, "một tỷ không trăm linh một"),
            (1_005_000_000, "một tỷ không trăm linh năm triệu"),
            (2_000_000_000_000, "hai nghìn tỷ"),
            (10_000_000_000_000, "mười nghìn tỷ"),
        ],
    )
    def test_tu_mot_ty_tro_len(self, value: int, expected: str) -> None:
        assert number_in_words(value) == expected


class TestVndInWords:
    def test_viet_hoa_chu_dau_va_them_don_vi(self) -> None:
        assert vnd_in_words(12_000_000) == "Mười hai triệu đồng Việt Nam"

    def test_so_le(self) -> None:
        assert vnd_in_words(3_600_000) == "Ba triệu sáu trăm nghìn đồng Việt Nam"

    @pytest.mark.parametrize("value", [0, -5])
    def test_khong_duong_thi_rong_chu_khong_viet_dong_khong(self, value: int) -> None:
        assert vnd_in_words(value) == ""

    def test_nhan_so_nguyen_dang_float(self) -> None:
        assert vnd_in_words(5_000_000.0) == "Năm triệu đồng Việt Nam"  # type: ignore[arg-type]
