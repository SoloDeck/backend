import uuid
from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import IntegrityError

from src.modules.users.application.service import UsersService
from src.modules.users.schemas.request import (
    ChangePasswordRequest,
    FreelancerProfileUpdateRequest,
)
from src.shared.exceptions.domain import (
    AlreadyExistsError,
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
    profile_slug: str | None = None
    status: str = "active"
    deleted_at: object | None = None


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


class TestCapNhatTenDuongDan:
    """Đặt `profile_slug` — chỗ duy nhất trong hồ sơ có ràng buộc UNIQUE dưới DB.

    Hai lớp chặn, cố ý: kiểm trước khi ghi để có thông điệp tử tế cho trường hợp thường,
    và bắt `IntegrityError` cho hai trường hợp mà bước kiểm không với tới — hai yêu cầu
    cùng lúc, và người giữ slug đã bị xoá mềm (ràng buộc UNIQUE không loại hàng đã xoá).
    Thiếu lớp sau thì người dùng thấy 500 cho một việc rất bình thường.
    """

    @staticmethod
    def _service(repo: AsyncMock):  # type: ignore[no-untyped-def]
        return UsersService(db=AsyncMock(), repo=repo, storage=AsyncMock())

    @staticmethod
    def _payload(slug: str):  # type: ignore[no-untyped-def]
        return FreelancerProfileUpdateRequest(profile_slug=slug)

    def _repo(self, *, taken: bool = False) -> AsyncMock:
        repo = AsyncMock()
        repo.get_by_id.return_value = UserStub(id=uuid.uuid4())
        repo.is_profile_slug_taken.return_value = taken
        repo.save.side_effect = lambda u: u
        return repo

    async def test_ten_da_co_nguoi_giu_thi_bao_409_va_khong_ghi(self) -> None:
        repo = self._repo(taken=True)

        with pytest.raises(AlreadyExistsError):
            await self._service(repo).update_freelancer_profile(
                uuid.uuid4(), self._payload("thu-thuy")
            )

        repo.save.assert_not_awaited()

    async def test_ten_con_trong_thi_ghi_binh_thuong(self) -> None:
        repo = self._repo()

        await self._service(repo).update_freelancer_profile(uuid.uuid4(), self._payload("thu-thuy"))

        repo.save.assert_awaited_once()

    async def test_thua_cuoc_dua_ghi_thi_van_ra_409_chu_khong_phai_500(self) -> None:
        """Bước kiểm báo còn trống nhưng DB chặn — người giữ đã xoá mềm, hoặc hai request đua."""
        repo = self._repo()
        repo.save.side_effect = IntegrityError(
            "INSERT ...",
            {},
            Exception('duplicate key violates unique constraint "uq_users_profile_slug"'),
        )

        with pytest.raises(AlreadyExistsError):
            await self._service(repo).update_freelancer_profile(
                uuid.uuid4(), self._payload("thu-thuy")
            )

    async def test_rang_buoc_khac_vo_thi_nem_tiep_chu_khong_doi_thanh_409(self) -> None:
        """Gán 409 "tên đã có người dùng" cho một ràng buộc khác là nói dối người dùng."""
        repo = self._repo()
        repo.save.side_effect = IntegrityError(
            "INSERT ...", {}, Exception('violates unique constraint "uq_users_phone"')
        )

        with pytest.raises(IntegrityError):
            await self._service(repo).update_freelancer_profile(
                uuid.uuid4(), self._payload("thu-thuy")
            )

    async def test_xoa_tai_khoan_thi_nha_ten_duong_dan_ra(self) -> None:
        """Không nhả thì tài khoản đã xoá ngồi giữ chỗ vĩnh viễn, chính chủ cũng không lấy lại."""
        user = UserStub(id=uuid.uuid4())
        user.profile_slug = "thu-thuy"
        repo = AsyncMock()
        repo.get_by_id.return_value = user
        repo.save.side_effect = lambda u: u

        await self._service(repo).delete_me(user.id)

        assert user.profile_slug is None
        assert user.status == "deleted"
