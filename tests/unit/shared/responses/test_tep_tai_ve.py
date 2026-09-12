"""Khoá lỗi: tải tệp đính kèm tên tiếng Việt có dấu là lỗi 500.

Header HTTP chỉ mang được latin-1. Trước bản sửa, tên tệp được nhét thẳng vào f-string nên
"báo giá gửi khách.pdf" làm Starlette ném UnicodeEncodeError lúc mã hoá header — người dùng
bấm tải về nhận đúng một lỗi 500 trống trơn. Mà người Việt đặt tên tệp tiếng Việt là
chuyện thường ngày.  #Huynh
"""

import pytest

from src.shared.responses.tep_tai_ve import TEN_MAC_DINH, content_disposition_dinh_kem


class TestContentDispositionDinhKem:
    @pytest.mark.parametrize(
        "ten",
        [
            "báo giá gửi khách.pdf",
            "hợp đồng số 01 — công ty Đại Việt.docx",
            "ảnh chụp màn hình 2026.png",
        ],
    )
    def test_ten_tieng_viet_luon_ma_hoa_duoc_sang_latin1(self, ten):
        # Đây CHÍNH LÀ bài kiểm tra lỗi 500: nếu header không mã hoá được sang latin-1
        # thì Starlette nổ đúng ở bước này.
        content_disposition_dinh_kem(ten).encode("latin-1")

    def test_giu_duoc_ten_that_qua_filename_sao(self):
        header = content_disposition_dinh_kem("báo giá.pdf")
        # Trình duyệt hiện nay ưu tiên filename*, nên người dùng vẫn nhận đúng tên có dấu.
        assert "filename*=UTF-8''b%C3%A1o%20gi%C3%A1.pdf" in header

    def test_ban_du_phong_ascii_van_doc_duoc(self):
        header = content_disposition_dinh_kem("báo giá.pdf")
        assert 'filename="bao gia.pdf"' in header

    def test_dau_cach_thanh_phan_tram_hai_muoi_chu_khong_thanh_dau_cong(self):
        # `quote_plus` sẽ cho ra dấu cộng và trình duyệt hiểu thành dấu cộng thật.
        assert "+" not in content_disposition_dinh_kem("hai tu.pdf")

    @pytest.mark.parametrize("ky_tu", ['"', "\r\n", "\\", "/"])
    def test_ky_tu_cat_duoc_header_bi_thay_the(self, ky_tu):
        # Tên tệp là chuỗi do người ngoài đặt lúc tải lên, nên phải coi là dữ liệu bẩn.
        header = content_disposition_dinh_kem(f"anh{ky_tu}chen.png")
        # Lấy đúng GIÁ TRỊ giữa hai dấu nháy, vì bản thân dấu nháy là dấu bao của header.
        gia_tri = header.split('filename="', 1)[1].split('"', 1)[0]
        assert ky_tu not in gia_tri
        # "\r\n" là HAI ký tự nên thành hai gạch dưới; số gạch phải khớp độ dài đầu vào.
        assert gia_tri == "anh" + "_" * len(ky_tu) + "chen.png"
        # Bản `filename*` giữ nguyên ký tự nhưng ở dạng mã hoá phần trăm nên vô hại.
        header.encode("latin-1")

    @pytest.mark.parametrize("ten", [None, "", "   ", "———"])
    def test_ten_rong_hoac_mat_sach_sau_khi_bo_dau_thi_co_ten_du_phong(self, ten):
        assert TEN_MAC_DINH in content_disposition_dinh_kem(ten)
