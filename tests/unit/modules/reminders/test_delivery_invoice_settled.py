"""Khâu giao thư KHÔNG nhắc thanh toán một hóa đơn đã thu đủ / đã hủy.

Bình thường lời nhắc đã bị hủy ngay lúc ghi nhận thu. Chốt chặn này lo cho đường nào lọt qua đó,
và cho cả lượt "Gửi ngay": nhắc khách trả khoản họ đã trả là cách nhanh nhất để mất khách.
"""

from unittest.mock import AsyncMock, patch

from src.modules.reminders.application import delivery_service as _delivery_mod
from tests.unit.modules.reminders.test_delivery_service import make_reminder, make_service

SETTLED = "invoice_is_settled"


def payment_reminder(**over):  # type: ignore[no-untyped-def]
    return make_reminder(target_type="invoice", reminder_type="payment_due", **over)


class TestBoQuaKhiDaThu:
    async def test_hoa_don_da_thu_du_thi_huy_loi_nhac_va_khong_gui_thu(self) -> None:
        reminder = payment_reminder()
        send_email = AsyncMock()
        service, _ = make_service(reminder, send_email=send_email)

        with patch.object(_delivery_mod, SETTLED, new=AsyncMock(return_value=True)):
            result = await service.deliver(reminder.id)

        assert result.status == "cancelled"
        assert result.delivered is False
        assert reminder.status == "cancelled"
        assert "nên SoloDesk không gửi lời nhắc nữa" in result.detail
        send_email.assert_not_awaited()

    async def test_con_no_thi_van_gui_nhu_cu(self) -> None:
        reminder = payment_reminder()
        send_email = AsyncMock()
        service, _ = make_service(reminder, send_email=send_email)

        with (
            patch.object(_delivery_mod, SETTLED, new=AsyncMock(return_value=False)),
            patch.object(
                _delivery_mod, "build_payment_section", new=AsyncMock(return_value=("", "", None))
            ),
            patch.object(
                _delivery_mod, "project_label_for", new=AsyncMock(return_value="English center")
            ),
        ):
            result = await service.deliver(reminder.id)

        assert result.status == "sent"
        send_email.assert_awaited_once()

    async def test_chan_thu_chay_truoc_buoc_gui_ke_ca_khi_bam_gui_ngay(self) -> None:
        """`unattended=False` là lượt tự bấm "Gửi ngay" — vẫn không được nhắc hóa đơn đã trả."""
        reminder = payment_reminder()
        send_email = AsyncMock()
        service, _ = make_service(reminder, send_email=send_email)

        with patch.object(_delivery_mod, SETTLED, new=AsyncMock(return_value=True)):
            result = await service.deliver(reminder.id, unattended=False)

        assert result.status == "cancelled"
        send_email.assert_not_awaited()


class TestChanThuNoiVeDuAn:
    async def test_chan_thu_ghi_ten_du_an_con_tieu_de_van_la_ma_hoa_don(self) -> None:
        reminder = payment_reminder()
        send_email = AsyncMock()
        service, _ = make_service(reminder, label="INV-20261003-3AF1", send_email=send_email)

        with (
            patch.object(_delivery_mod, SETTLED, new=AsyncMock(return_value=False)),
            patch.object(
                _delivery_mod, "build_payment_section", new=AsyncMock(return_value=("", "", None))
            ),
            patch.object(
                _delivery_mod, "project_label_for", new=AsyncMock(return_value="English center")
            ),
        ):
            await service.deliver(reminder.id)

        kwargs = send_email.await_args.kwargs
        assert kwargs["subject"] == "Nhắc thanh toán INV-20261003-3AF1"
        assert "Về dự án: English center." in kwargs["plain"]
        assert "Về dự án: INV-" not in kwargs["plain"]
