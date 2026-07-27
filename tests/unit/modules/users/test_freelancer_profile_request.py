"""Gói 2 — validator nghề trên FreelancerProfileUpdateRequest.

Chốt: slug hợp lệ đi qua, None (bỏ chọn) hợp lệ, không set thì không nằm trong
model_fields_set (nên service sẽ không đụng tới), slug sai bị từ chối.
"""

import pytest
from pydantic import ValidationError

from src.modules.users.schemas.request import FreelancerProfileUpdateRequest


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
