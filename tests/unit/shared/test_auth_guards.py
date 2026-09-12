"""Khoá chốt chặn nhịp gọi ở ba cửa xác thực.

Trước bản sửa, `FixedWindowRateLimiter` có sẵn trong repo nhưng chỉ được gắn cho biểu mẫu
tiếp nhận công khai — ba cửa `/auth/login`, `/auth/password-reset/request` và
`/auth/password-reset/confirm` nhận số lần gọi không giới hạn. Bài này khoá lại để không ai
gỡ mất.  #Huynh
"""

import pytest

from src.shared.exceptions.domain import RateLimitError
from src.shared.rate_limit.auth_guards import (
    chan_nhip_dang_nhap,
    chan_nhip_go_ma,
    chan_nhip_xin_ma,
    dia_chi_goi_den,
    reset_moi_bo_dem,
)
from src.shared.rate_limit.limiter import FixedWindowRateLimiter


class _RequestGia:
    """Đủ giống Request cho phần chốt chặn cần: headers và client."""

    def __init__(self, ip: str = "1.2.3.4", chuyen_tiep: str | None = None):
        self.headers = {"x-forwarded-for": chuyen_tiep} if chuyen_tiep else {}
        self.client = type("C", (), {"host": ip})()


@pytest.fixture(autouse=True)
def _don_bo_dem():
    reset_moi_bo_dem()
    yield
    reset_moi_bo_dem()


class TestDiaChiGoiDen:
    def test_uu_tien_x_forwarded_for_vi_deploy_that_co_nginx_dung_truoc(self):
        # Không đọc header này thì sau nginx mọi người chung một địa chỉ nội bộ,
        # chốt chặn thành ra chặn nhầm toàn bộ người dùng thật.
        req = _RequestGia(ip="10.0.0.9", chuyen_tiep="203.0.113.7, 10.0.0.1")
        assert dia_chi_goi_den(req) == "203.0.113.7"

    def test_khong_co_header_thi_dung_dia_chi_ket_noi(self):
        assert dia_chi_goi_den(_RequestGia(ip="198.51.100.5")) == "198.51.100.5"

    def test_khong_biet_dia_chi_thi_van_tra_ve_mot_khoa_on_dinh(self):
        req = _RequestGia()
        req.client = None
        assert dia_chi_goi_den(req) == "khong-ro"


class TestChanNhip:
    def test_dang_nhap_cung_mot_tai_khoan_bi_chan_sau_10_luot(self):
        req = _RequestGia()
        for _ in range(10):
            chan_nhip_dang_nhap(req, "nan-nhan@example.com")
        with pytest.raises(RateLimitError):
            chan_nhip_dang_nhap(req, "nan-nhan@example.com")

    def test_doi_hoa_thuong_email_khong_lach_duoc_tran(self):
        # Không chuẩn hoá thì "A@x.com" và "a@x.com" thành hai rổ riêng, trần nhân đôi.
        req = _RequestGia()
        for i in range(10):
            chan_nhip_dang_nhap(req, "Nan-Nhan@example.com" if i % 2 else "nan-nhan@example.com")
        with pytest.raises(RateLimitError):
            chan_nhip_dang_nhap(req, "NAN-NHAN@EXAMPLE.COM")

    def test_xin_ma_otp_chan_rat_som_vi_moi_luot_la_mot_la_thu_that(self):
        req = _RequestGia()
        for _ in range(3):
            chan_nhip_xin_ma(req, "ai-do@example.com")
        with pytest.raises(RateLimitError) as loi:
            chan_nhip_xin_ma(req, "ai-do@example.com")
        # Câu báo đi thẳng ra màn hình nên phải là tiếng Việt và nói được bước tiếp theo.
        assert "OTP" in loi.value.message
        assert "spam" in loi.value.message

    def test_go_ma_sai_bi_chan_theo_dia_chi_may_goi(self):
        req = _RequestGia()
        for _ in range(10):
            chan_nhip_go_ma(req)
        with pytest.raises(RateLimitError):
            chan_nhip_go_ma(req)

    def test_hai_may_khac_nhau_khong_lam_anh_huong_nhau(self):
        for _ in range(10):
            chan_nhip_go_ma(_RequestGia(ip="1.1.1.1"))
        chan_nhip_go_ma(_RequestGia(ip="2.2.2.2"))  # không được ném


class TestDonKhoaHetHan:
    def test_khoa_khong_ai_cham_lai_khong_nam_lai_mai_trong_bo_nho(self):
        """Khoá do người ngoài đặt (token trong URL, địa chỉ IP) nên bơm phình được.

        `check` chỉ dọn dấu thời gian của đúng khoá đang gọi, nên trước bản sửa một khoá
        không bao giờ được chạm lại sẽ nằm đó mãi — bắn vào link bịa, mỗi lần một chuỗi
        khác nhau, là bào hết RAM tiến trình.
        """
        dong_ho = {"t": 0.0}
        bo_dem = FixedWindowRateLimiter(
            max_requests=5,
            window_seconds=10,
            time_func=lambda: dong_ho["t"],
            max_keys_before_sweep=50,
        )
        for i in range(60):
            bo_dem.check(f"link-bia-{i}")

        dong_ho["t"] = 1000.0  # mọi dấu thời gian cũ đều đã hết hạn
        bo_dem.check("mot-luot-that")

        assert len(bo_dem._hits) == 1, "phải quét sạch khoá hết hạn, chỉ giữ lượt vừa gọi"

    def test_khoa_con_han_khong_bi_quet_nham(self):
        dong_ho = {"t": 0.0}
        bo_dem = FixedWindowRateLimiter(
            max_requests=5,
            window_seconds=10_000,
            time_func=lambda: dong_ho["t"],
            max_keys_before_sweep=10,
        )
        for i in range(20):
            bo_dem.check(f"khoa-{i}")
        assert len(bo_dem._hits) == 20
