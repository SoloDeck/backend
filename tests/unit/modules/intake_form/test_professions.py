"""Gói 1 — chốt hành vi danh mục nghề để gói 2–3 dựa vào không sợ vỡ.

Test qua ĐÚNG API công khai (`all_professions`/`is_valid_profession`/`profession_label`),
không đụng dict nội bộ — giữ đúng tinh thần seam: đổi ruột sau này test vẫn xanh.
"""

import re

from src.modules.intake_form.professions import (
    all_professions,
    is_valid_profession,
    profession_label,
    profession_scam_hint,
)


def test_co_6_nghe():
    assert len(all_professions()) == 6


def test_moi_muc_co_value_va_label_khong_rong():
    for item in all_professions():
        assert item["value"] and item["value"].strip()
        assert item["label"] and item["label"].strip()


def test_slug_sach_an_toan_cho_db_va_url():
    # Chỉ chữ thường / số / gạch ngang / '&' — không dấu, không khoảng trắng.
    #
    # '&' được cho qua vì slug PHẢI trùng tên thư mục dưới `src/ai/knowledge/professions/`
    # (`photography&videography`) để retriever tra được kiến thức theo nghề. Đổi slug thì
    # phải đổi cả tên thư mục và các test intake form đang chốt đúng danh sách này.
    #
    # LƯU Ý: '&' chưa escape mà đem ghép vào query string thì vỡ
    # (`?profession=photography&videography` bị tách thành hai tham số). Nay slug chỉ đi
    # trong JSON body nên chưa ảnh hưởng — nhưng nếu sau này lọc theo nghề bằng query
    # param thì phải đổi slug thành `photography-videography` (kèm đổi tên thư mục).
    for item in all_professions():
        assert re.fullmatch(r"[a-z0-9&-]+", item["value"]), item["value"]


def test_validate_slug():
    assert is_valid_profession("ui-ux-design")
    assert is_valid_profession(None)  # chưa chọn nghề = hợp lệ
    assert not is_valid_profession("phi-hanh-gia")


def test_lay_nhan_tieng_viet():
    assert profession_label("graphic-design") == "Thiết kế đồ hoạ"
    assert profession_label(None) is None
    assert profession_label("khong-co-slug-nay") is None


def test_scam_hint_theo_nghe():
    # Mỗi nghề trong danh mục đều có gợi ý scam đặc thù (để lead qualifier cảnh báo).
    for item in all_professions():
        assert profession_scam_hint(item["value"])
    # Chưa chọn / không tồn tại -> None.
    assert profession_scam_hint(None) is None
    assert profession_scam_hint("khong-co-slug-nay") is None
