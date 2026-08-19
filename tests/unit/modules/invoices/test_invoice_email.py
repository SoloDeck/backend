"""Thư hóa đơn gửi khách — nội dung, và luật "gửi hỏng thì không đánh dấu đã gửi"."""

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from src.modules.invoices.application.emails import build_invoice_email, format_vnd
from src.modules.invoices.application.service import InvoicesService
from src.shared.exceptions.domain import BusinessRuleError, EmailDeliveryError

SEND_EMAIL = "src.shared.email.smtp.send_email"


def an_email(**overrides):  # type: ignore[no-untyped-def]
    data = {
        "client_name": "Công ty Nắng",
        "freelancer_name": "Huỳnh Hòa",
        "invoice_number": "INV-20260804-A1B2",
        "line_items": [("Đặt cọc khi ký hợp đồng", Decimal(15_000_000))],
        "total": Decimal(15_000_000),
        "amount_due": Decimal(15_000_000),
        "issue_date": date(2026, 8, 4),
        "due_date": date(2026, 8, 18),
    }
    data.update(overrides)
    return build_invoice_email(**data)


class TestNoiDungThu:
    def test_tieu_de_khong_gan_tien_to_solodesk(self) -> None:
        """Thư này là freelancer gửi khách của mình, không phải hệ thống thông báo —
        cùng lý do với `reminders.build_subject`. Gắn tên phần mềm vào là lộ ra máy gửi."""
        content = an_email()
        assert "[SoloDesk]" not in content.subject
        assert "INV-20260804-A1B2" in content.subject
        assert "Huỳnh Hòa" in content.subject

    def test_thu_tu_du_de_khach_tra_tien(self) -> None:
        """Khách KHÔNG có tài khoản trong hệ thống và sẽ không đăng nhập vào đâu cả. Thiếu
        một trong bốn thứ này là khách phải nhắn lại hỏi."""
        content = an_email()
        for phai_co in ("INV-20260804-A1B2", "15.000.000 ₫", "18/08/2026", "Công ty Nắng"):
            assert phai_co in content.html, phai_co
            assert phai_co in content.plain, phai_co

    def test_da_thu_mot_phan_thi_doi_dung_phan_con_lai(self) -> None:
        """Gửi lại mà vẫn ghi nguyên tổng là đòi khách trả hai lần phần họ đã chuyển."""
        content = an_email(total=Decimal(15_000_000), amount_due=Decimal(5_000_000))
        assert "Còn phải thanh toán" in content.html
        assert "5.000.000 ₫" in content.html
        # Tổng vẫn phải in ra để khách đối chiếu, chỉ là không phải số cần chuyển.
        assert "15.000.000 ₫" in content.html

    def test_chua_thu_dong_nao_thi_khong_bay_ra_hai_con_so(self) -> None:
        content = an_email()
        assert "Còn phải thanh toán" not in content.html
        assert "Tổng cộng" in content.html

    def test_escape_moi_thu_nguoi_dung_go(self) -> None:
        """Tên khách và nhãn hạng mục do người dùng gõ; một dấu `<` là vỡ HTML thư gửi khách."""
        content = an_email(
            client_name='Cty <script>alert("x")</script> & Co',
            line_items=[("Thiết kế <b>logo</b>", Decimal(1_000_000))],
        )
        assert "<script>" not in content.html
        assert "&lt;script&gt;" in content.html
        assert "<b>logo</b>" not in content.html

    def test_format_tien_kieu_viet_nam(self) -> None:
        assert format_vnd(Decimal(15_000_000)) == "15.000.000 ₫"
        assert format_vnd(0) == "0 ₫"

    def test_khoi_thanh_toan_va_anh_duoc_nhung_vao(self) -> None:
        content = an_email(
            payment_html="<table>QR ở đây</table>",
            payment_plain="THANH TOÁN CHO TÔI",
            images_html='<img src="cid:img0">',
            footer="Gửi từ Huỳnh Hòa qua SoloDesk.",
        )
        assert "QR ở đây" in content.html
        assert 'src="cid:img0"' in content.html
        assert "THANH TOÁN CHO TÔI" in content.plain
        assert "qua SoloDesk" in content.plain


@dataclass
class InvoiceStub:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    owner_user_id: uuid.UUID = field(default_factory=uuid.uuid4)
    client_id: uuid.UUID = field(default_factory=uuid.uuid4)
    invoice_number: str = "INV-1"
    status: str = "draft"
    total: Decimal = Decimal(1_000_000)
    subtotal: Decimal = Decimal(1_000_000)
    amount_paid: Decimal = Decimal(0)
    issue_date: date = date(2026, 8, 4)
    due_date: date = date(2026, 8, 18)
    notes: str | None = None
    sent_at: object | None = None
    share_token: str | None = None


@dataclass
class ClientStub:
    name: str = "Công ty Nắng"
    email: str | None = "khach@example.com"


@dataclass
class OwnerStub:
    full_name: str = "Huỳnh Hòa"
    email: str = "freelancer@example.com"
    bank_code: str | None = "970436"
    bank_account_number: str | None = "1234567890"
    bank_account_holder: str | None = "HUYNH HOA"
    momo_phone_number: str | None = None
    bank_account_info: str | None = None


def a_service(invoice: InvoiceStub):  # type: ignore[no-untyped-def]
    repo = AsyncMock()
    repo.get_by_id.return_value = invoice
    repo.get_client_by_id.return_value = ClientStub()
    repo.get_owner.return_value = OwnerStub()
    repo.list_line_items.return_value = []
    repo.save.side_effect = lambda obj: obj
    return InvoicesService(db=AsyncMock(), repo=repo), repo


class TestGuiHoaDon:
    async def test_gui_that_va_danh_dau_da_gui(self) -> None:
        invoice = InvoiceStub()
        service, _ = a_service(invoice)

        with patch(SEND_EMAIL, new=AsyncMock()) as send_email:
            await service.send(invoice.owner_user_id, invoice.id)

        send_email.assert_awaited_once()
        assert invoice.status == "sent"
        assert invoice.share_token, "phải sinh token để sau này còn dựng link xem hóa đơn"
        # Gửi THAY MẶT freelancer: khách thấy tên họ và bấm Trả lời là về đúng hộp thư họ.
        kwargs = send_email.await_args.kwargs
        assert kwargs["from_name"] == "Huỳnh Hòa"
        assert kwargs["reply_to"] == "freelancer@example.com"
        assert kwargs["to"] == "khach@example.com"

    async def test_gui_hong_thi_khong_danh_dau_da_gui(self) -> None:
        """Đây là luật quan trọng nhất của lần sửa này.

        Bản trước `send()` chỉ đổi trạng thái và KHÔNG hề gửi thư, nên nút "Gửi cho khách"
        là một lời nói dối. Nay thư không đi được thì hóa đơn phải ở nguyên `draft` — thà
        để freelancer biết mà gửi lại, còn hơn để họ ngồi đợi một khoản tiền mà khách không
        biết là phải trả."""
        invoice = InvoiceStub()
        service, _ = a_service(invoice)

        with (
            patch(SEND_EMAIL, new=AsyncMock(side_effect=EmailDeliveryError("hỏng", "connect"))),
            pytest.raises(EmailDeliveryError),
        ):
            await service.send(invoice.owner_user_id, invoice.id)

        assert invoice.status == "draft"
        assert invoice.sent_at is None

    async def test_notify_false_chi_danh_dau_khong_gui(self) -> None:
        """Freelancer đã tự gửi tay qua Zalo/Messenger rồi, chỉ muốn hệ thống ghi nhận."""
        invoice = InvoiceStub()
        service, _ = a_service(invoice)

        with patch(SEND_EMAIL, new=AsyncMock()) as send_email:
            await service.send(invoice.owner_user_id, invoice.id, notify=False)

        send_email.assert_not_awaited()
        assert invoice.status == "sent"

    async def test_khach_chua_co_email_thi_bao_ro_chu_khong_no(self) -> None:
        invoice = InvoiceStub()
        service, repo = a_service(invoice)
        repo.get_client_by_id.return_value = ClientStub(email=None)

        with (
            patch(SEND_EMAIL, new=AsyncMock()),
            pytest.raises(BusinessRuleError, match="chưa có email"),
        ):
            await service.send(invoice.owner_user_id, invoice.id)

        assert invoice.status == "draft"

    async def test_khong_co_anh_dinh_kem_thi_kem_qr_tu_sinh(self) -> None:
        invoice = InvoiceStub()
        service, _ = a_service(invoice)

        with patch(SEND_EMAIL, new=AsyncMock()) as send_email:
            await service.send(invoice.owner_user_id, invoice.id)

        assert "vietqr" in (send_email.await_args.kwargs["inline_images"] or {})

    async def test_co_anh_rieng_thi_khong_kem_qr_tu_sinh(self) -> None:
        """Hai mã QR cạnh nhau là khách phải phân vân quét cái nào — đoán sai thì tiền đi
        nhầm chỗ."""
        invoice = InvoiceStub()
        service, _ = a_service(invoice)
        attachments = [{"key": "u/1.png", "filename": "qr.png", "content_type": "image/png"}]

        with (
            patch(
                "src.modules.reminders.application.attachments.load_image_bytes",
                new=AsyncMock(return_value={"img0": b"\x89PNG"}),
            ),
            patch(SEND_EMAIL, new=AsyncMock()) as send_email,
        ):
            await service.send(invoice.owner_user_id, invoice.id, attachments=attachments)

        images = send_email.await_args.kwargs["inline_images"] or {}
        assert "img0" in images
        assert "vietqr" not in images
