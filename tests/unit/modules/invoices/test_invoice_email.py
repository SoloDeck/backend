"""Thư hóa đơn gửi khách — nội dung, và luật "gửi hỏng thì không đánh dấu đã gửi"."""

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from src.modules.invoices.application.emails import (
    build_invoice_email,
    build_invoice_footer,
    fill_amount_placeholder,
    format_vnd,
    strip_invoice_title_line,
)
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


class TestTenDuAnTrongThu:
    """Thư nói rõ hóa đơn này CHO DỰ ÁN NÀO.

    Hóa đơn chỉ ghi tên hạng mục ("Thanh toán đợt 1") và số tiền; khách làm nhiều dự án với cùng
    một freelancer thì đọc thư không biết khoản tiền này của việc nào.  #Huynh
    """

    def test_cau_mo_dau_neu_ten_du_an_o_ca_hai_ban(self) -> None:
        content = an_email(project_name="Website bán hàng")
        assert 'Huỳnh Hòa gửi bạn hóa đơn INV-20260804-A1B2 cho dự án "Website bán hàng".' in (
            content.plain
        )
        assert (
            "gửi bạn hóa đơn <strong>INV-20260804-A1B2</strong>"
            ' cho dự án <strong>"Website bán hàng"</strong>.'
        ) in content.html

    def test_khong_ten_nguoi_gui_van_neu_ten_du_an(self) -> None:
        content = an_email(freelancer_name=None, project_name="Website bán hàng")
        assert 'Đây là hóa đơn INV-20260804-A1B2 cho dự án "Website bán hàng".' in content.plain
        assert 'cho dự án <strong>"Website bán hàng"</strong>.' in content.html

    @pytest.mark.parametrize("ten", [None, "", "   "])
    def test_khong_co_ten_du_an_thi_cau_mo_dau_nhu_cu(self, ten) -> None:  # type: ignore[no-untyped-def]
        """Không bịa ra tên: thiếu thì im lặng, thư vẫn đủ ý."""
        content = an_email(project_name=ten)
        assert "cho dự án" not in content.plain
        assert "cho dự án" not in content.html
        assert "Huỳnh Hòa gửi bạn hóa đơn INV-20260804-A1B2." in content.plain

    def test_escape_ten_du_an_trong_html(self) -> None:
        """Tên dự án do người dùng gõ, giống tên khách: một dấu `<` là vỡ HTML thư gửi khách."""
        content = an_email(project_name='Cty <script>x</script> & "Co"')
        assert "<script>" not in content.html
        assert "&lt;script&gt;" in content.html
        assert 'Cty <script>x</script> & "Co"' in content.plain  # bản chữ thuần không phải HTML


class TestChanThuHoaDon:
    """Chân thư: ai gửi, về dự án nào, và khách KHÔNG cần trả lời.

    Hai lỗi thật của chân thư dùng chung: dòng "Về dự án" từng ghi MÃ HÓA ĐƠN ("Về dự án: Hóa đơn
    INV-…") nên khách đọc ra một cái tên dự án không có thật; và dòng cuối mời khách "trả lời email
    này, thư sẽ về thẳng hộp thư" trong khi hóa đơn là thư thông báo, khách chỉ cần chuyển khoản.
    """

    def test_ba_dong_dung_chu(self) -> None:
        footer = build_invoice_footer("Huỳnh Hòa", "hoa@example.com", "Website bán hàng")
        assert footer.splitlines() == [
            "Email này được gửi từ Huỳnh Hòa (hoa@example.com) qua SoloDesk.",
            "Về dự án: Website bán hàng.",
            "Bạn không cần trả lời email này.",
        ]

    def test_khong_con_loi_moi_khach_tra_loi(self) -> None:
        footer = build_invoice_footer("Huỳnh Hòa", "hoa@example.com", "Website bán hàng")
        assert "Bạn trả lời email này" not in footer
        assert "thư sẽ về thẳng" not in footer

    def test_khong_co_ten_du_an_thi_bo_dong_ve_du_an(self) -> None:
        footer = build_invoice_footer("Huỳnh Hòa", "hoa@example.com", None)
        assert "Về dự án" not in footer
        assert footer.splitlines()[-1] == "Bạn không cần trả lời email này."

    def test_thieu_email_nguoi_gui_thi_chi_ghi_ten(self) -> None:
        footer = build_invoice_footer("Huỳnh Hòa", None, "Website bán hàng")
        assert footer.splitlines()[0] == "Email này được gửi từ Huỳnh Hòa qua SoloDesk."

    def test_khong_biet_nguoi_gui_thi_khong_co_chan_thu(self) -> None:
        # Cùng lối với chân thư dùng chung: không có tên người gửi thì không dựng chân thư.
        assert build_invoice_footer(None, "hoa@example.com", "Website bán hàng") == ""
        assert build_invoice_footer("   ", None, None) == ""

    def test_chan_thu_di_vao_ca_hai_ban_cua_thu(self) -> None:
        content = an_email(
            footer=build_invoice_footer("Huỳnh Hòa", "hoa@example.com", "Website bán hàng")
        )
        for ban in (content.plain, content.html):
            assert "Bạn không cần trả lời email này." in ban
            assert "Về dự án: Website bán hàng." in ban


class TestDongTenNoiBoKhongLotRaThu:
    """Dòng đầu `notes` "Hóa đơn: <tên>" là chỗ web CẤT tên hóa đơn, không phải lời gửi khách.

    Lỗi thật: mục Ghi chú của thư tới khách mở đầu bằng "Hóa đơn: Thanh toán đợt 1" rồi mới tới
    lời chào.  #Huynh
    """

    TIEU_DE = "Hóa đơn: Thanh toán đợt 1\n\n"

    def test_dong_ten_khong_xuat_hien_trong_thu(self) -> None:
        content = an_email(notes=self.TIEU_DE + "Kính gửi Công ty Nắng,\nCảm ơn anh.")
        for ban in (content.plain, content.html):
            assert "Thanh toán đợt 1" not in ban
        assert "Ghi chú: Kính gửi Công ty Nắng,\nCảm ơn anh." in content.plain
        assert "Kính gửi Công ty Nắng," in content.html

    def test_chi_co_dong_ten_thi_thu_khong_co_khoi_ghi_chu(self) -> None:
        content = an_email(notes="Hóa đơn: Thanh toán đợt 1")
        assert "Ghi chú" not in content.plain
        assert "Thanh toán đợt 1" not in content.plain
        assert "border-left:3px solid #4f46e5" not in content.html  # khung Ghi chú của bản HTML

    def test_xuong_dong_kieu_windows_va_nhieu_dong_trong(self) -> None:
        content = an_email(notes="Hóa đơn: Đợt 2\r\n\r\n\r\nLời nhắn.")
        assert "Đợt 2" not in content.plain
        assert "Ghi chú: Lời nhắn." in content.plain

    def test_khong_phan_biet_hoa_thuong_giong_ben_web(self) -> None:
        content = an_email(notes="HÓA ĐƠN: Đợt 3\n\nLời nhắn.")
        assert "Đợt 3" not in content.plain
        assert "Ghi chú: Lời nhắn." in content.plain

    def test_chu_hoa_don_o_giua_loi_nhan_la_loi_cua_freelancer_nen_giu(self) -> None:
        content = an_email(notes=self.TIEU_DE + "Hóa đơn: này nhớ thanh toán đúng hạn.")
        assert "Ghi chú: Hóa đơn: này nhớ thanh toán đúng hạn." in content.plain

    def test_ghi_chu_khong_co_dong_ten_thi_giu_nguyen_van(self) -> None:
        # "Hóa đơn tháng 8" không có dấu hai chấm ngay sau nên không phải dòng tên.
        content = an_email(notes="Hóa đơn tháng 8, cảm ơn anh.")
        assert "Ghi chú: Hóa đơn tháng 8, cảm ơn anh." in content.plain

    def test_so_trong_dong_ten_khong_chan_gui(self) -> None:
        # Khách không thấy dòng tên, nên một con số nằm trong đó không làm thư lệch gì.
        content = an_email(notes="Hóa đơn: Đợt 1 — 99.999.000\n\nCảm ơn anh.")
        assert "99.999.000" not in content.plain

    def test_so_lech_trong_loi_nhan_van_bi_chan_sau_khi_bo_dong_ten(self) -> None:
        with pytest.raises(BusinessRuleError):
            an_email(notes=self.TIEU_DE + "Tổng cộng 99.999.000 ₫.")

    def test_ham_bo_dong_ten_truc_tiep(self) -> None:
        assert strip_invoice_title_line(None) is None
        assert strip_invoice_title_line("") == ""
        assert strip_invoice_title_line("Hóa đơn: A\n\nB") == "B"
        assert strip_invoice_title_line("  Hóa đơn: A\n\n  B  ") == "B"
        assert strip_invoice_title_line("Hóa đơn: A") == ""
        # Không có dòng tên thì trả đúng văn bản gốc, kể cả khoảng trắng hai đầu.
        assert strip_invoice_title_line("  Chỉ có lời nhắn.  ") == "  Chỉ có lời nhắn.  "
        # "Hóa đơn:" trống tên thì web cũng không coi là dòng tên.
        assert strip_invoice_title_line("Hóa đơn:\n\nB") == "Hóa đơn:\n\nB"


class TestSoTienTrongLoiNhan:
    """Số tiền trong lời nhắn tự gõ do SERVER điền, không nhận số người dùng gõ vào chữ.

    Lỗi thật: ô "Số tiền trước thuế" = 521.900.000 nhưng văn bản ghi 511.900.000; thư tới khách
    mang cả hai con số, còn mã QR theo số thứ nhất.  #Huynh
    """

    def test_cho_giu_cho_duoc_dien_dung_so_cua_hoa_don(self) -> None:
        content = an_email(
            total=Decimal(521_900_000),
            amount_due=Decimal(521_900_000),
            line_items=[("abc", Decimal(521_900_000))],
            notes="Tổng số tiền cần thanh toán là {{tong_tien}}.",
        )
        assert "Tổng số tiền cần thanh toán là 521.900.000 ₫." in content.plain
        assert "Tổng số tiền cần thanh toán là 521.900.000 ₫." in content.html
        assert "{{" not in content.plain and "{{" not in content.html

    def test_khoang_trang_va_hoa_thuong_khong_lam_hong_cho_giu_cho(self) -> None:
        content = an_email(notes="Cần trả {{ TONG_TIEN }} nhé, {{tong_tien}} đó.")
        assert "Cần trả 15.000.000 ₫ nhé, 15.000.000 ₫ đó." in content.plain

    def test_dien_theo_so_con_phai_tra_khi_da_thu_mot_phan(self) -> None:
        content = an_email(
            total=Decimal(15_000_000),
            amount_due=Decimal(5_000_000),
            notes="Còn {{tong_tien}}.",
        )
        assert "Còn 5.000.000 ₫." in content.plain

    def test_khong_co_cho_giu_cho_thi_giu_nguyen_van(self) -> None:
        content = an_email(notes="Cảm ơn anh đã hợp tác.")
        assert "Ghi chú: Cảm ơn anh đã hợp tác." in content.plain

    def test_chan_gui_khi_loi_nhan_ghi_so_tien_khac_hoa_don(self) -> None:
        """Đúng ca người dùng gặp: ô số tiền 521.900.000 nhưng văn bản gõ 511.900.000."""
        with pytest.raises(BusinessRuleError) as exc:
            an_email(
                total=Decimal(521_900_000),
                amount_due=Decimal(521_900_000),
                line_items=[("abc", Decimal(521_900_000))],
                notes="Tổng số tiền cần thanh toán là 511.900.000 ₫.",
            )
        message = str(exc.value)
        assert "511.900.000 ₫" in message
        assert "521.900.000 ₫" in message
        assert "xem xét lại" in message  # nói người dùng phải làm gì

    def test_cho_qua_khi_so_gõ_tay_khop_hoa_don(self) -> None:
        content = an_email(
            total=Decimal(108_000_000),
            amount_due=Decimal(108_000_000),
            line_items=[("Thiết kế", Decimal(100_000_000))],
            notes="Tạm tính 100.000.000 ₫, thuế 8.000.000 ₫, tổng 108.000.000 ₫.",
        )
        assert "tổng 108.000.000 ₫" in content.plain

    def test_so_tran_nhu_dien_thoai_ngay_thang_khong_bi_chan(self) -> None:
        content = an_email(notes="Gọi 0352015349 trước 16/10/2026 nhé, mã đợt 2.")
        assert "0352015349" in content.plain

    def test_cho_giu_cho_luon_qua_cua_chan(self) -> None:
        # Điền xong là đúng số hóa đơn nên không thể lệch.
        content = an_email(notes="Tổng {{tong_tien}} và {{tong_tien}} nhé.")
        assert "Tổng 15.000.000 ₫ và 15.000.000 ₫ nhé." in content.plain

    def test_fill_amount_placeholder_chiu_duoc_rong_va_none(self) -> None:
        assert fill_amount_placeholder(None, 1) is None
        assert fill_amount_placeholder("", 1) == ""
        assert fill_amount_placeholder("a {{tong_tien}} b", 1_500_000) == "a 1.500.000 ₫ b"


@dataclass
class InvoiceStub:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    owner_user_id: uuid.UUID = field(default_factory=uuid.uuid4)
    client_id: uuid.UUID = field(default_factory=uuid.uuid4)
    deal_id: uuid.UUID | None = field(default_factory=uuid.uuid4)
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
class DealStub:
    title: str = "Website bán hàng"


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
    repo.get_deal_by_id.return_value = DealStub()
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

    async def test_thu_gui_di_mang_ten_du_an_that_va_khong_moi_tra_loi(self) -> None:
        """Đúng thứ khách nhận: tên dự án THẬT ở câu mở đầu và chân thư, không phải mã hóa đơn."""
        invoice = InvoiceStub(invoice_number="INV-20261002-6C15")
        service, repo = a_service(invoice)

        with patch(SEND_EMAIL, new=AsyncMock()) as send_email:
            await service.send(invoice.owner_user_id, invoice.id)

        kwargs = send_email.await_args.kwargs
        for ban in (kwargs["plain"], kwargs["html"]):
            assert "Website bán hàng" in ban
            assert "Bạn không cần trả lời email này." in ban
            assert "thư sẽ về thẳng" not in ban
        assert 'hóa đơn INV-20261002-6C15 cho dự án "Website bán hàng".' in kwargs["plain"]
        assert "Về dự án: Website bán hàng." in kwargs["plain"]
        assert "Về dự án: Hóa đơn" not in kwargs["plain"]  # lỗi cũ: mã hóa đơn đóng vai tên dự án
        # Tra deal theo ĐÚNG chủ hóa đơn: không để tên dự án của người khác lọt vào thư.
        repo.get_deal_by_id.assert_awaited_once_with(invoice.deal_id, invoice.owner_user_id)
        # Dặn "không cần trả lời" chứ không chặn: khách lỡ bấm Trả lời thì thư vẫn về hộp
        # freelancer.
        assert kwargs["reply_to"] == "freelancer@example.com"

    async def test_thu_gui_di_khong_lot_dong_ten_noi_bo_va_khong_mat_ten_da_luu(self) -> None:
        notes = "Hóa đơn: Thanh toán đợt 1\n\nCảm ơn anh đã hợp tác."
        invoice = InvoiceStub(notes=notes)
        service, _ = a_service(invoice)

        with patch(SEND_EMAIL, new=AsyncMock()) as send_email:
            await service.send(invoice.owner_user_id, invoice.id)

        kwargs = send_email.await_args.kwargs
        for ban in (kwargs["plain"], kwargs["html"]):
            assert "Thanh toán đợt 1" not in ban
            assert "Cảm ơn anh đã hợp tác." in ban
        # Chỉ thư bị lược; tên hóa đơn lưu trong `notes` vẫn nguyên để web còn đọc ra.
        assert invoice.notes == notes

    async def test_hoa_don_khong_gan_deal_van_gui_duoc_khong_co_ten_du_an(self) -> None:
        invoice = InvoiceStub(deal_id=None)
        service, repo = a_service(invoice)

        with patch(SEND_EMAIL, new=AsyncMock()) as send_email:
            await service.send(invoice.owner_user_id, invoice.id)

        repo.get_deal_by_id.assert_not_awaited()
        plain = send_email.await_args.kwargs["plain"]
        assert "cho dự án" not in plain
        assert "Về dự án" not in plain
        assert "Bạn không cần trả lời email này." in plain
        assert invoice.status == "sent"

    @pytest.mark.parametrize("deal", [None, DealStub(title="   ")])
    async def test_deal_da_xoa_hoac_ten_trong_thi_van_gui_duoc(self, deal) -> None:  # type: ignore[no-untyped-def]
        invoice = InvoiceStub()
        service, repo = a_service(invoice)
        repo.get_deal_by_id.return_value = deal

        with patch(SEND_EMAIL, new=AsyncMock()) as send_email:
            await service.send(invoice.owner_user_id, invoice.id)

        plain = send_email.await_args.kwargs["plain"]
        assert "cho dự án" not in plain
        assert "Về dự án" not in plain
        assert invoice.status == "sent"

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
