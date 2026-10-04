"""Gửi hóa đơn thì tự đặt lời nhắc thanh toán; thu đủ hoặc hủy thì hủy lời nhắc đó.

Phần dựng lời nhắc nằm ở `reminders/application/invoice_reminders.py` (có test riêng). Ở đây chỉ
khoá CHỖ NỐI: dịch vụ hóa đơn gọi nó đúng lúc, đúng tham số, và không gọi khi không nên.
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.modules.invoices.schemas.request import PaymentRequest
from src.modules.reminders.application.invoice_reminders import PaymentReminderOutcome
from src.shared.exceptions.domain import EmailDeliveryError
from tests.unit.modules.invoices.test_invoice_email import SEND_EMAIL, InvoiceStub, a_service

BASE = "src.modules.reminders.application.invoice_reminders."
SCHEDULE = BASE + "schedule_invoice_payment_reminder"
RETIRE = BASE + "retire_invoice_payment_reminders"
REFRESH = BASE + "refresh_invoice_reminder_amounts"
REMAINING = BASE + "remaining_amount_text"


def scheduled_outcome() -> PaymentReminderOutcome:
    return PaymentReminderOutcome(
        reminder=SimpleNamespace(scheduled_at=datetime(2026, 10, 14, 2, 0, tzinfo=UTC)),
        days_before_due=3,
        requires_approval=True,
    )


class TestDatLoiNhacKhiGui:
    async def test_xin_dat_loi_nhac_thi_goi_dung_sau_khi_da_ghi_trang_thai_da_gui(self) -> None:
        invoice = InvoiceStub()
        service, repo = a_service(invoice)

        with (
            patch(SEND_EMAIL, new=AsyncMock()),
            patch(SCHEDULE, new=AsyncMock(return_value=scheduled_outcome())) as schedule,
        ):
            await service.send(invoice.owner_user_id, invoice.id, schedule_payment_reminder=True)

        schedule.assert_awaited_once()
        kwargs = schedule.await_args.kwargs
        assert kwargs["invoice"] is invoice
        assert kwargs["invoice"].status == "sent", "phải đặt SAU khi đã ghi trạng thái đã gửi"
        assert kwargs["client"] is repo.get_client_by_id.return_value
        assert kwargs["owner"] is repo.get_owner.return_value

    async def test_khong_xin_thi_khong_dat(self) -> None:
        """Client cũ gọi trần vẫn chạy y như trước, không tự nhiên sinh lời nhắc gửi khách."""
        invoice = InvoiceStub()
        service, _ = a_service(invoice)

        with patch(SEND_EMAIL, new=AsyncMock()), patch(SCHEDULE, new=AsyncMock()) as schedule:
            saved = await service.send(invoice.owner_user_id, invoice.id)

        schedule.assert_not_awaited()
        assert getattr(saved, "payment_reminder", None) is None

    async def test_phan_hoi_mang_ket_qua_de_web_noi_dung(self) -> None:
        """Web dựa vào đây để nói "đã lên lịch" hay vì sao chưa lên lịch được."""
        invoice = InvoiceStub()
        service, _ = a_service(invoice)

        with (
            patch(SEND_EMAIL, new=AsyncMock()),
            patch(SCHEDULE, new=AsyncMock(return_value=scheduled_outcome())),
        ):
            saved = await service.send(
                invoice.owner_user_id, invoice.id, schedule_payment_reminder=True
            )

        assert saved.payment_reminder == {
            "scheduled": True,
            "scheduled_at": datetime(2026, 10, 14, 2, 0, tzinfo=UTC),
            "days_before_due": 3,
            "requires_approval": True,
            "reason": None,
        }

    async def test_khong_dat_duoc_thi_phan_hoi_neu_ly_do_va_hoa_don_van_la_da_gui(self) -> None:
        invoice = InvoiceStub()
        service, _ = a_service(invoice)

        with (
            patch(SEND_EMAIL, new=AsyncMock()),
            patch(
                SCHEDULE,
                new=AsyncMock(
                    return_value=PaymentReminderOutcome(reason="too_soon", days_before_due=3)
                ),
            ),
        ):
            saved = await service.send(
                invoice.owner_user_id, invoice.id, schedule_payment_reminder=True
            )

        assert saved.status == "sent"
        assert saved.payment_reminder["scheduled"] is False
        assert saved.payment_reminder["reason"] == "too_soon"

    async def test_gui_hong_thi_khong_dat_loi_nhac(self) -> None:
        """Thư không đi được thì hóa đơn ở nguyên nháp — không có hóa đơn đã gửi nào để mà nhắc."""
        invoice = InvoiceStub()
        service, _ = a_service(invoice)

        with (
            patch(SEND_EMAIL, new=AsyncMock(side_effect=EmailDeliveryError("hỏng", "connect"))),
            patch(SCHEDULE, new=AsyncMock()) as schedule,
            pytest.raises(EmailDeliveryError),
        ):
            await service.send(invoice.owner_user_id, invoice.id, schedule_payment_reminder=True)

        schedule.assert_not_awaited()
        assert invoice.status == "draft"

    async def test_ghi_nhan_da_gui_tay_van_dat_loi_nhac(self) -> None:
        """Freelancer tự gửi qua Zalo rồi chỉ ghi nhận: khách vẫn cần được nhắc nếu chưa trả."""
        invoice = InvoiceStub()
        service, _ = a_service(invoice)

        with (
            patch(SEND_EMAIL, new=AsyncMock()) as send_email,
            patch(SCHEDULE, new=AsyncMock(return_value=scheduled_outcome())) as schedule,
        ):
            await service.send(
                invoice.owner_user_id, invoice.id, notify=False, schedule_payment_reminder=True
            )

        send_email.assert_not_awaited()
        schedule.assert_awaited_once()


class TestHuyVaCapNhatLoiNhac:
    @staticmethod
    def sent_invoice() -> InvoiceStub:
        return InvoiceStub(status="sent", total=Decimal(1_000_000))

    @staticmethod
    def payment(amount: int) -> PaymentRequest:
        return PaymentRequest(amount=Decimal(amount), payment_date=date(2026, 10, 5))

    async def test_thu_du_thi_huy_loi_nhac_dang_cho(self) -> None:
        invoice = self.sent_invoice()
        service, _ = a_service(invoice)

        with (
            patch(RETIRE, new=AsyncMock()) as retire,
            patch(REFRESH, new=AsyncMock()) as refresh,
            patch(REMAINING, new=lambda _inv: "x"),
        ):
            saved = await service.record_payment(
                invoice.owner_user_id, invoice.id, self.payment(1_000_000)
            )

        assert saved.status == "paid"
        retire.assert_awaited_once()
        assert retire.await_args.kwargs == {
            "owner_user_id": invoice.owner_user_id,
            "invoice_id": invoice.id,
        }
        refresh.assert_not_awaited()

    async def test_thu_mot_phan_thi_giu_loi_nhac_va_doi_so_tien_trong_chu(self) -> None:
        """Lời nhắc đặt từ lúc gửi có thể chờ nhiều ngày; số "còn lại" trong chữ phải theo kịp."""
        invoice = self.sent_invoice()
        service, _ = a_service(invoice)
        texts = iter(["1.000.000 ₫", "600.000 ₫"])  # trước rồi sau khi ghi nhận

        with (
            patch(RETIRE, new=AsyncMock()) as retire,
            patch(REFRESH, new=AsyncMock()) as refresh,
            patch(REMAINING, new=lambda _inv: next(texts)),
        ):
            saved = await service.record_payment(
                invoice.owner_user_id, invoice.id, self.payment(400_000)
            )

        assert saved.status == "partially_paid"
        retire.assert_not_awaited()
        refresh.assert_awaited_once()
        assert refresh.await_args.kwargs == {
            "owner_user_id": invoice.owner_user_id,
            "invoice_id": invoice.id,
            "old_text": "1.000.000 ₫",
            "new_text": "600.000 ₫",
        }

    async def test_huy_hoa_don_thi_huy_loi_nhac(self) -> None:
        invoice = self.sent_invoice()
        service, _ = a_service(invoice)

        with patch(RETIRE, new=AsyncMock()) as retire:
            saved = await service.void(invoice.owner_user_id, invoice.id)

        assert saved.status == "void"
        retire.assert_awaited_once()
