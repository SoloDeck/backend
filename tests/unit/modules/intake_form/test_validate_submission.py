"""Unit tests cho vòng kiểm trường bắt buộc của biểu mẫu tiếp nhận công khai.

Bài khoá lỗi: freelancer thêm một trường tự tạo (`custom-...`) rồi gạt Bắt buộc thì biểu
mẫu công khai chết hẳn — khách điền đủ mọi ô vẫn ăn 422 kèm khoá nội bộ, vì khoá tự tạo
không bao giờ có mặt trong body mà vòng kiểm vẫn đòi nó.
"""

import uuid
from dataclasses import dataclass, field

import pytest

from src.modules.deals.schemas.request import PublicIntakeRequest
from src.modules.intake_form.application.service import IntakeFormService
from src.shared.exceptions.domain import ValidationError


@dataclass
class _FakeUser:
    id: uuid.UUID


@dataclass
class _FakeField:
    field_key: str
    label: str
    is_required: bool = False
    is_visible: bool = True


@dataclass
class _FakeConfig:
    id: uuid.UUID
    is_active: bool = True


@dataclass
class _FakeRepo:
    """Repo giả — vòng kiểm này không chạm DB nên không cần PostgreSQL."""

    fields: list[_FakeField] = field(default_factory=list)
    is_active: bool = True
    user: _FakeUser = field(default_factory=lambda: _FakeUser(id=uuid.uuid4()))

    async def get_user_by_token(self, share_token: str):
        return self.user

    async def get_by_owner(self, owner_user_id: uuid.UUID):
        return _FakeConfig(id=uuid.uuid4(), is_active=self.is_active)

    async def get_visible_fields(self, form_id: uuid.UUID):
        return [f for f in self.fields if f.is_visible]


def _service(repo: _FakeRepo) -> IntakeFormService:
    return IntakeFormService(db=None, repo=repo)


async def test_truong_tu_tao_bat_buoc_khong_lam_chet_form_cong_khai():
    """Khoá tự tạo không nằm trong body -> không được coi là bỏ trống."""
    repo = _FakeRepo(
        fields=[
            _FakeField("name", "Họ tên khách hàng", is_required=True),
            _FakeField("inquiry_text", "Mô tả nhu cầu", is_required=True),
            _FakeField("custom-1757290123456-7", "Bạn biết tôi qua đâu?", is_required=True),
        ]
    )
    payload = PublicIntakeRequest(name="Lan", inquiry_text="Cần thiết kế logo")

    await _service(repo).validate_submission("tok", payload)


async def test_truong_chuan_bat_buoc_de_trong_van_bi_chan():
    repo = _FakeRepo(
        fields=[
            _FakeField("name", "Họ tên khách hàng", is_required=True),
            _FakeField("phone", "Số điện thoại", is_required=True),
        ]
    )
    payload = PublicIntakeRequest(name="Lan")

    with pytest.raises(ValidationError) as err:
        await _service(repo).validate_submission("tok", payload)

    assert "Số điện thoại" in str(err.value)


async def test_cau_loi_dung_nhan_freelancer_dat_khong_phun_khoa_noi_bo():
    repo = _FakeRepo(fields=[_FakeField("project_name", "Tên dự án", is_required=True)])
    payload = PublicIntakeRequest(name="Lan")

    with pytest.raises(ValidationError) as err:
        await _service(repo).validate_submission("tok", payload)

    message = str(err.value)
    assert "Tên dự án" in message
    assert "project_name" not in message


async def test_truong_tu_tao_bat_buoc_nhung_an_di_cung_khong_chan():
    repo = _FakeRepo(
        fields=[
            _FakeField("name", "Họ tên khách hàng", is_required=True),
            _FakeField("custom-1-2", "Câu hỏi ẩn", is_required=True, is_visible=False),
        ]
    )
    payload = PublicIntakeRequest(name="Lan")

    await _service(repo).validate_submission("tok", payload)
