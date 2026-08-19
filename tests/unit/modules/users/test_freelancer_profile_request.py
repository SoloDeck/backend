"""Gói 2 — validator nghề trên FreelancerProfileUpdateRequest.

Chốt: slug hợp lệ đi qua, None (bỏ chọn) hợp lệ, không set thì không nằm trong
model_fields_set (nên service sẽ không đụng tới), slug sai bị từ chối.
"""

import pytest
from pydantic import ValidationError

from src.modules.users.schemas.request import (
    FreelancerProfileUpdateRequest,
    UpdateUserRequest,
)


def test_profession_slug_hop_le():
    req = FreelancerProfileUpdateRequest(profession="ui-ux-design")
    assert req.profession == "ui-ux-design"


def test_profession_none_la_hop_le():
    req = FreelancerProfileUpdateRequest(profession=None)
    assert req.profession is None


def test_khong_set_profession_thi_khong_bi_dung_toi():
    req = FreelancerProfileUpdateRequest(professional_title="Freelancer")
    assert req.profession is None
    assert "profession" not in req.model_fields_set


def test_profession_sai_bi_tu_choi():
    with pytest.raises(ValidationError):
        FreelancerProfileUpdateRequest(profession="phi-hanh-gia")


class TestChanDuongDanAnh:
    """`avatar_url` và `cover_url` phải theo cùng một luật.

    Cả hai đều đổ thẳng vào thuộc tính src của thẻ img trên trang ai cũng mở được, nên để
    mỗi trường một luật là kiểu gì cũng có ngày lệch. `UpdateUserRequest.avatar_url` trước
    đây không có cả giới hạn độ dài lẫn kiểm lược đồ — mà màn onboarding ghi avatar qua
    đúng đường đó.
    """

    @pytest.mark.parametrize("field", ["avatar_url", "cover_url"])
    @pytest.mark.parametrize(
        "value", ["data:image/jpeg;base64,abc", "https://lh3.googleusercontent.com/a/x"]
    )
    def test_du_lieu_anh_va_link_https_thi_qua(self, field: str, value: str):
        req = FreelancerProfileUpdateRequest(**{field: value})
        assert getattr(req, field) == value

    @pytest.mark.parametrize("field", ["avatar_url", "cover_url"])
    @pytest.mark.parametrize(
        "value", ["javascript:alert(1)", "http://vi-du.vn/a.png", "data:text/html,x"]
    )
    def test_luoc_do_la_bi_tu_choi(self, field: str, value: str):
        with pytest.raises(ValidationError):
            FreelancerProfileUpdateRequest(**{field: value})

    @pytest.mark.parametrize("field", ["avatar_url", "cover_url"])
    def test_chuoi_rong_thanh_none_de_xoa_duoc_anh(self, field: str):
        assert getattr(FreelancerProfileUpdateRequest(**{field: ""}), field) is None

    @pytest.mark.parametrize("field", ["avatar_url", "cover_url"])
    def test_qua_dai_thi_bi_tu_choi(self, field: str):
        with pytest.raises(ValidationError):
            FreelancerProfileUpdateRequest(**{field: "data:image/png;base64," + "a" * 1_500_001})


class TestUpdateUserRequestCungLuat:
    """Đường `PATCH /users/me` cũng ghi avatar, nên cũng phải có đủ hai chốt."""

    def test_luoc_do_la_bi_tu_choi(self):
        with pytest.raises(ValidationError):
            UpdateUserRequest(avatar_url="javascript:alert(1)")

    def test_qua_dai_thi_bi_tu_choi(self):
        with pytest.raises(ValidationError):
            UpdateUserRequest(avatar_url="data:image/png;base64," + "a" * 1_500_001)

    def test_du_lieu_anh_thi_qua(self):
        req = UpdateUserRequest(avatar_url="data:image/png;base64,abc")
        assert req.avatar_url == "data:image/png;base64,abc"
