"""Thư gửi khách kèm báo giá: câu chữ, tiêu đề, và không để người dùng gõ vỡ HTML."""

from src.modules.proposals.application.emails import build_proposal_email


def _build(**overrides):  # type: ignore[no-untyped-def]
    args = {
        "client_name": "Anh Minh",
        "freelancer_name": "Huỳnh Hoa",
        "project_name": "Website đặt lịch phòng khám",
        "total": "173.000.000 ₫",
        "valid_until": "31/10/2026",
        "footer": "Email này được gửi từ Huỳnh Hoa qua SoloDesk.",
    }
    args.update(overrides)
    return build_proposal_email(**args)


class TestTieuDe:
    def test_neu_ten_du_an_va_nguoi_gui(self) -> None:
        assert _build().subject == "Báo giá dự án Website đặt lịch phòng khám từ Huỳnh Hoa"

    def test_khong_gan_tien_to_solodesk(self) -> None:
        """Đây là freelancer gửi cho khách của mình, không phải thư hệ thống."""
        assert "SoloDesk" not in _build().subject

    def test_thieu_ten_du_an_hoac_nguoi_gui_thi_van_la_tieu_de_hop_le(self) -> None:
        mail = _build(project_name=None, freelancer_name="  ")
        assert mail.subject == "Báo giá dịch vụ"


class TestThanThu:
    def test_nhac_khach_mo_file_pdf_dinh_kem(self) -> None:
        mail = _build()
        assert "PDF đính kèm" in mail.plain
        assert "PDF đính kèm" in mail.html

    def test_in_tong_gia_tri_va_han_hieu_luc_dung_nhu_tren_to_bao_gia(self) -> None:
        mail = _build()
        assert "Tổng giá trị: 173.000.000 ₫" in mail.plain
        assert "Báo giá có hiệu lực đến: 31/10/2026" in mail.plain
        assert "173.000.000 ₫" in mail.html and "31/10/2026" in mail.html

    def test_thieu_gia_hoac_han_thi_bo_dong_do_thay_vi_de_trong(self) -> None:
        mail = _build(total="", valid_until=None)
        assert "Tổng giá trị" not in mail.plain
        assert "hiệu lực" not in mail.plain
        assert "Tổng giá trị" not in mail.html

    def test_chan_thu_co_ten_va_email_that_cua_freelancer(self) -> None:
        mail = _build()
        assert "Huỳnh Hoa qua SoloDesk" in mail.plain
        assert "Huỳnh Hoa qua SoloDesk" in mail.html

    def test_khach_biet_tra_loi_thang_email_nay(self) -> None:
        assert "trả lời thẳng email này" in _build().plain


class TestAnToanHtml:
    def test_ten_khach_va_ten_du_an_do_nguoi_dung_go_phai_duoc_escape(self) -> None:
        mail = _build(client_name="A & <B>", project_name='Logo "X" <script>')
        assert "<script>" not in mail.html
        assert "A &amp; &lt;B&gt;" in mail.html
        # Bản chữ thuần thì giữ nguyên chữ người dùng gõ.
        assert "A & <B>" in mail.plain
