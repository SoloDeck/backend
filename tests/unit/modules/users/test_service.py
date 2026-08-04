import uuid
from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest

from src.modules.users.application.service import UsersService
from src.modules.users.schemas.request import ChangePasswordRequest
from src.shared.exceptions.domain import (
    AuthenticationError,
    NotFoundError,
    ValidationError,
)
from src.shared.security.passwords import hash_password, verify_password


@dataclass
class UserStub:
    id: uuid.UUID
    avatar_url: str | None = None
    hashed_password: str | None = None


class TestDatVaDoiMatKhau:
    """Đặt mật khẩu lần đầu (tài khoản Google) và đổi mật khẩu đang có.

    Ranh giới giữa hai nhánh là chỗ dễ làm sai nhất: `current_password` khai tuỳ chọn ở tầng
    schema để tài khoản Google gửi được, nhưng tài khoản ĐÃ CÓ mật khẩu thì vẫn phải bắt buộc.
    Hụt chốt chặn đó là ai cướp được phiên cũng đổi được mật khẩu người khác.
    """

    @staticmethod
    def _service(user: UserStub):  # type: ignore[no-untyped-def]
        repo = AsyncMock()
        repo.get_by_id.return_value = user
        repo.save.side_effect = lambda u: u
        return UsersService(db=AsyncMock(), repo=repo, storage=AsyncMock())

    async def test_chua_co_mat_khau_thi_dat_duoc_ma_khong_can_mat_khau_cu(self) -> None:
        """Tài khoản đăng nhập bằng Google: `hashed_password=None`, không có gì để nhập."""
        user = UserStub(id=uuid.uuid4(), hashed_password=None)
        service = self._service(user)

        await service.change_password(user.id, ChangePasswordRequest(new_password="MatKhauMoi2026"))

        assert user.hashed_password is not None
        assert verify_password("MatKhauMoi2026", user.hashed_password)

    async def test_da_co_mat_khau_ma_khong_gui_mat_khau_cu_thi_bi_tu_choi(self) -> None:
        """Ca bảo mật quan trọng nhất của cả thay đổi này.

        `current_password` tuỳ chọn ở schema, nên nếu service không TỰ kiểm trường hợp thiếu
        thì một phiên bị đánh cắp là đủ để đổi mật khẩu nạn nhân."""
        cu = hash_password("MatKhauCu2026")
        user = UserStub(id=uuid.uuid4(), hashed_password=cu)
        service = self._service(user)

        with pytest.raises(AuthenticationError):
            await service.change_password(
                user.id, ChangePasswordRequest(new_password="KeXauTuDat2026")
            )

        assert user.hashed_password == cu, "mật khẩu KHÔNG được đổi"

    async def test_da_co_mat_khau_ma_gui_sai_mat_khau_cu_thi_bi_tu_choi(self) -> None:
        cu = hash_password("MatKhauCu2026")
        user = UserStub(id=uuid.uuid4(), hashed_password=cu)
        service = self._service(user)

        with pytest.raises(AuthenticationError):
            await service.change_password(
                user.id,
                ChangePasswordRequest(current_password="doan-bua", new_password="MatKhauMoi2026"),
            )

        assert user.hashed_password == cu, "mật khẩu KHÔNG được đổi"

    async def test_da_co_mat_khau_va_gui_dung_thi_doi_duoc(self) -> None:
        user = UserStub(id=uuid.uuid4(), hashed_password=hash_password("MatKhauCu2026"))
        service = self._service(user)

        await service.change_password(
            user.id,
            ChangePasswordRequest(current_password="MatKhauCu2026", new_password="MatKhauMoi2026"),
        )

        assert verify_password("MatKhauMoi2026", user.hashed_password)


class TestUploadAvatar:
    async def test_uploads_and_sets_avatar_url(self) -> None:
        user_id = uuid.uuid4()
        user = UserStub(id=user_id)
        repo = AsyncMock()
        repo.get_by_id.return_value = user
        repo.save.side_effect = lambda u: u
        storage = AsyncMock()
        storage.upload.return_value = "https://cdn.example.com/avatars/x/y.png"
        service = UsersService(db=AsyncMock(), repo=repo, storage=storage)

        result = await service.upload_avatar(
            user_id, content=b"fake-bytes", content_type="image/png"
        )

        storage.upload.assert_awaited_once()
        assert result.avatar_url == "https://cdn.example.com/avatars/x/y.png"

    async def test_rejects_unsupported_content_type(self) -> None:
        repo = AsyncMock()
        storage = AsyncMock()
        service = UsersService(db=AsyncMock(), repo=repo, storage=storage)

        with pytest.raises(ValidationError):
            await service.upload_avatar(
                uuid.uuid4(), content=b"fake-bytes", content_type="application/pdf"
            )
        storage.upload.assert_not_awaited()

    async def test_rejects_empty_file(self) -> None:
        repo = AsyncMock()
        storage = AsyncMock()
        service = UsersService(db=AsyncMock(), repo=repo, storage=storage)

        with pytest.raises(ValidationError):
            await service.upload_avatar(uuid.uuid4(), content=b"", content_type="image/png")

    async def test_rejects_oversized_file(self) -> None:
        repo = AsyncMock()
        storage = AsyncMock()
        service = UsersService(db=AsyncMock(), repo=repo, storage=storage)
        oversized = b"x" * (5 * 1024 * 1024 + 1)

        with pytest.raises(ValidationError):
            await service.upload_avatar(uuid.uuid4(), content=oversized, content_type="image/png")

    async def test_raises_not_found_for_unknown_user(self) -> None:
        repo = AsyncMock()
        repo.get_by_id.return_value = None
        storage = AsyncMock()
        service = UsersService(db=AsyncMock(), repo=repo, storage=storage)

        with pytest.raises(NotFoundError):
            await service.upload_avatar(
                uuid.uuid4(), content=b"fake-bytes", content_type="image/png"
            )

    async def test_raises_runtime_error_when_storage_not_initialized(self) -> None:
        repo = AsyncMock()
        service = UsersService(db=AsyncMock(), repo=repo)

        with pytest.raises(RuntimeError):
            await service.upload_avatar(
                uuid.uuid4(), content=b"fake-bytes", content_type="image/png"
            )
