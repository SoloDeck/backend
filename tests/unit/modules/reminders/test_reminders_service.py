"""Chốt chặn quyền sở hữu ở `POST /reminders`.

`target_id` tới thẳng từ body. Đây là endpoint GHI duy nhất còn nhận lưu một id trỏ sang
dữ liệu người khác — invoices, proposals, contracts, ai_jobs, tasks đều đã kiểm. Chưa rò
dữ liệu (mọi đường ĐỌC đều lọc theo chủ), nhưng người dùng gặp: API trả 201 "đã đặt
lịch", lời nhắc nằm ở Chờ gửi, tới giờ mới hỏng với câu nói SAI nguyên nhân.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.modules.reminders.application.service import RemindersService
from src.modules.reminders.schemas.request import CreateReminderRequest
from src.shared.exceptions.domain import NotFoundError


def make_payload(target_type: str = "deal", target_id: uuid.UUID | None = None):  # type: ignore[no-untyped-def]
    return CreateReminderRequest(
        target_type=target_type,  # type: ignore[arg-type]
        target_id=target_id or uuid.uuid4(),
        reminder_type="follow_up",
        channel="email",
        scheduled_at=datetime.now(UTC) + timedelta(days=1),
        message_preview="Chào anh, dự án tới đâu rồi ạ?",
    )


def make_service(resolved):  # type: ignore[no-untyped-def]
    repo = AsyncMock()
    repo.resolve_target.return_value = resolved
    return RemindersService(db=AsyncMock(), repo=repo), repo


class TestCreateKiemChuSoHuu:
    async def test_dat_lich_tren_du_an_nguoi_khac_thi_bao_khong_tim_thay(self) -> None:
        service, repo = make_service((None, None))

        with pytest.raises(NotFoundError):
            await service.create(uuid.uuid4(), make_payload())

        # Quan trọng nhất: KHÔNG ghi gì vào bảng reminders.
        repo.create.assert_not_awaited()

    async def test_kiem_theo_nguoi_dang_goi_chu_khong_theo_body(self) -> None:
        service, repo = make_service((None, None))
        caller = uuid.uuid4()

        with pytest.raises(NotFoundError):
            await service.create(caller, make_payload())

        assert repo.resolve_target.await_args.kwargs["owner_user_id"] == caller

    async def test_cau_bao_loi_tieng_viet_goi_dung_ten_loai_doi_tuong(self) -> None:
        service, _ = make_service((None, None))

        with pytest.raises(NotFoundError) as err:
            await service.create(uuid.uuid4(), make_payload(target_type="invoice"))

        message = str(err.value)
        assert "hoá đơn" in message
        # Không được lặp lại câu nói sai nguyên nhân của khâu gửi.
        assert "đã bị xoá" not in message

    async def test_doi_tuong_cua_chinh_minh_thi_dat_lich_binh_thuong(self) -> None:
        service, repo = make_service((MagicMock(), "Thiết kế logo"))
        payload = make_payload()

        await service.create(uuid.uuid4(), payload)

        repo.create.assert_awaited_once()
        assert repo.create.await_args.kwargs["target_id"] == payload.target_id

    async def test_du_an_con_do_nhung_khach_da_bi_xoa_thi_van_cho_dat_lich(self) -> None:
        """`resolve_target` trả (None, nhãn) khi deal còn mà khách đã mất — deal vẫn là
        của người này, không được chặn."""
        service, repo = make_service((None, "Thiết kế logo"))

        await service.create(uuid.uuid4(), make_payload())

        repo.create.assert_awaited_once()
