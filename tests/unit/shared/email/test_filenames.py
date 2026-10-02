"""Tên file đính kèm: chữ thường không dấu, đọc được ở mọi trình đọc mail."""

import pytest

from src.shared.email.filenames import attachment_filename


@pytest.mark.parametrize(
    ("prefix", "label", "mong_doi"),
    [
        ("bao-gia", "Website đặt lịch phòng khám", "bao-gia-website-dat-lich-phong-kham.pdf"),
        ("hop-dong", "Thiết kế logo & nhận diện", "hop-dong-thiet-ke-logo-nhan-dien.pdf"),
        ("bao-gia", "ĐẶNG  Văn   Đạt!!!", "bao-gia-dang-van-dat.pdf"),
    ],
)
def test_bo_dau_va_noi_bang_gach_ngang(prefix: str, label: str, mong_doi: str) -> None:
    assert attachment_filename(prefix, label) == mong_doi


@pytest.mark.parametrize("label", [None, "", "   ", "!!!", "日本語"])
def test_khong_co_ten_dung_duoc_thi_chi_con_tien_to(label: str | None) -> None:
    """Vẫn là một tên hợp lệ, không phải `bao-gia-.pdf`."""
    assert attachment_filename("bao-gia", label) == "bao-gia.pdf"


def test_ten_qua_dai_bi_cat_va_khong_ket_thuc_bang_gach_ngang() -> None:
    name = attachment_filename("bao-gia", "Dự án " + "rất dài " * 40)
    stem = name.removesuffix(".pdf")
    assert len(stem) <= len("bao-gia-") + 60
    assert not stem.endswith("-")
    assert name.isascii()
