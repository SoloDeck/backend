"""Thư gửi khách kèm hợp đồng: nói rõ việc khách cần làm tiếp, và không vỡ HTML."""

from src.modules.contracts.application.emails import build_contract_email


def _build(**overrides):  # type: ignore[no-untyped-def]
    args = {
        "client_name": "Anh Minh",
        "freelancer_name": "Huỳnh Hoa",
        "project_name": "Website đặt lịch phòng khám",
        "contract_number": "HD-2026-001",
        "footer": "Email này được gửi từ Huỳnh Hoa qua SoloDesk.",
    }
    args.update(overrides)
    return build_contract_email(**args)


class TestTieuDe:
    def test_neu_ten_du_an_va_nguoi_gui(self) -> None:
        assert _build().subject == "Hợp đồng dự án Website đặt lịch phòng khám từ Huỳnh Hoa"

    def test_khong_gan_tien_to_solodesk(self) -> None:
        assert "SoloDesk" not in _build().subject

    def test_thieu_ten_du_an_hoac_nguoi_gui_thi_van_la_tieu_de_hop_le(self) -> None:
        assert _build(project_name="", freelancer_name=None).subject == "Hợp đồng dịch vụ"


class TestThanThu:
    def test_noi_ro_khach_phai_doc_ky_roi_gui_lai_ban_da_ky(self) -> None:
        """Khách không ký trong hệ thống: hai bên ký ngoài rồi freelancer ghi nhận."""
        mail = _build()
        assert "file PDF đính kèm" in mail.plain
        assert "ký rồi gửi lại" in mail.plain
        assert "ký rồi gửi lại" in mail.html

    def test_khong_hua_hen_ky_tren_he_thong(self) -> None:
        mail = _build()
        assert "bấm vào" not in mail.plain.lower()
        assert "đăng nhập" not in mail.plain.lower()

    def test_neu_so_hop_dong_khi_co(self) -> None:
        assert "(số HD-2026-001/HĐDV)" in _build().plain
        assert "(số" not in _build(contract_number="").plain

    def test_chan_thu_co_ten_va_email_that_cua_freelancer(self) -> None:
        assert "Huỳnh Hoa qua SoloDesk" in _build().plain


class TestAnToanHtml:
    def test_gia_tri_nguoi_dung_go_phai_duoc_escape(self) -> None:
        mail = _build(client_name="A & <B>", project_name="<img src=x>")
        assert "<img" not in mail.html
        assert "A &amp; &lt;B&gt;" in mail.html


class TestSoHopDongKhopTrenGiay:
    def test_hau_to_trong_thu_la_dung_hau_to_in_tren_to_hop_dong(self) -> None:
        """Thư nêu "HD-2026-001/HĐDV" còn tờ giấy in "HD-2026-001" thì hai bên nhắc tới hai mã
        khác nhau. Hằng số trong thư phải trùng với chữ nằm ngay sau số hợp đồng trong template."""
        from pathlib import Path

        from src.modules.contracts.application.emails import CONTRACT_NUMBER_SUFFIX

        template = Path("src/ai/contract_generator/templates/contract.html").read_text(
            encoding="utf-8"
        )
        assert "{{ contract_number or \"……\" }}" + CONTRACT_NUMBER_SUFFIX in template
