"""Khoá chốt chặn: staging/production không được chạy bằng khoá bí mật mặc định.

Bối cảnh vì sao có bài này: `Settings` bật `env_ignore_empty=True`, nên một biến môi
trường RỖNG (pipeline ghi `JWT_SECRET_KEY=` khi GitHub secret chưa đặt) rơi êm về giá trị
mặc định `"change-me"` mà không một dòng log nào. Khi đó ai cũng tự ký được token
`role: admin`. Bài này khoá lại hành vi "chết ngay lúc khởi động" để không ai gỡ mất.  #Huynh
"""

import pytest
from pydantic import ValidationError

from src.config.settings import Settings

KHOA_THAT = {
    "secret_key": "k" * 40,
    "jwt_secret_key": "j" * 40,
}
KHOA_CONG_THAT = {
    "zalopay_key1": "z" * 32,
    "zalopay_key2": "y" * 32,
    "momo_access_key": "m" * 20,
    "momo_secret_key": "n" * 32,
}


# Mọi biến môi trường có thể che mất giá trị mặc định mà bài test này muốn kiểm.
_BIEN_CAN_DON = (
    "APP_ENV",
    "SECRET_KEY",
    "JWT_SECRET_KEY",
    "ZALOPAY_KEY1",
    "ZALOPAY_KEY2",
    "MOMO_ACCESS_KEY",
    "MOMO_SECRET_KEY",
)


@pytest.fixture(autouse=True)
def _moi_truong_sach(monkeypatch):
    """Gỡ các biến môi trường liên quan trước mỗi bài.

    `_env_file=None` chỉ tắt việc đọc file `.env`, KHÔNG chặn biến môi trường — nên trên CI
    (nơi `ci.yml` đặt sẵn `SECRET_KEY`/`JWT_SECRET_KEY` dài 32 ký tự hợp lệ) bài "khoá mặc
    định phải làm chết staging" lại thấy khoá thật và không có lỗi nào để bắt. Chạy ở máy
    thì xanh, lên CI thì đỏ. Dọn sạch ở đây để bài test kiểm đúng GIÁ TRỊ MẶC ĐỊNH trong
    code, không phải giá trị của máy đang chạy.  #Huynh
    """
    for ten in _BIEN_CAN_DON:
        monkeypatch.delenv(ten, raising=False)


def _dung(**ghi_de):
    """Dựng Settings bỏ qua .env của máy lập trình viên để bài test không phụ thuộc máy."""
    return Settings(_env_file=None, **ghi_de)


class TestChanKhoaMacDinh:
    def test_development_van_chay_duoc_voi_khoa_mac_dinh(self):
        # Máy lập trình viên không phải đặt biến môi trường mới chạy được.
        assert _dung(app_env="development").app_env == "development"

    @pytest.mark.parametrize("moi_truong", ["staging", "production"])
    def test_khoa_ky_mac_dinh_lam_chet_ca_staging_lan_production(self, moi_truong):
        with pytest.raises(ValidationError) as loi:
            _dung(app_env=moi_truong)
        assert "JWT_SECRET_KEY" in str(loi.value)

    @pytest.mark.parametrize("moi_truong", ["staging", "production"])
    def test_khoa_ky_ngan_hon_32_ky_tu_cung_bi_chan(self, moi_truong):
        with pytest.raises(ValidationError) as loi:
            _dung(app_env=moi_truong, secret_key="k" * 40, jwt_secret_key="ngan")
        assert "32" in str(loi.value)

    def test_khoa_cong_sandbox_khong_chan_production_khoi_dong(self):
        """Quyết định có cân nhắc: cảnh báo, KHÔNG chặn. Đừng "siết cho chặt".

        Khoá sandbox ZaloPay/MoMo là công khai nên dùng ở production đúng là rủi ro —
        người ngoài giả được callback để tự nâng gói miễn phí. Nhưng `ci.yml` không truyền
        `ZALOPAY_KEY1/KEY2` cho bất kỳ môi trường nào và nhóm chưa có tài khoản merchant
        thật, nên điều kiện KHÔNG BAO GIỜ thoả được. Chốt chặn không có đường đi qua thì
        không còn là chốt bảo vệ, nó chỉ khoá đường deploy của chính mình.

        Bài này khoá lại quyết định đó: production PHẢI khởi động được.  #Huynh
        """
        cau_hinh = _dung(app_env="production", **KHOA_THAT)
        assert cau_hinh.is_production is True

    def test_production_dung_khoa_sandbox_thi_bao_ten_tung_khoa(self):
        # Không chặn thì phải kêu to — `main.py` đọc danh sách này để log mức error.
        canh_bao = _dung(app_env="production", **KHOA_THAT).khoa_cong_dung_sandbox
        assert "ZALOPAY_KEY1" in canh_bao
        assert "ZALOPAY_KEY2" in canh_bao
        assert "MOMO_SECRET_KEY" in canh_bao

    def test_production_du_khoa_cong_that_thi_khong_canh_bao(self):
        cau_hinh = _dung(app_env="production", **KHOA_THAT, **KHOA_CONG_THAT)
        assert cau_hinh.khoa_cong_dung_sandbox == []

    def test_staging_khong_canh_bao_khoa_cong(self):
        # Staging vốn chỉ cần cổng sandbox — kêu ở đây là kêu oan mỗi lần khởi động.
        assert _dung(app_env="staging", **KHOA_THAT).khoa_cong_dung_sandbox == []

    def test_production_du_khoa_that_thi_qua(self):
        cau_hinh = _dung(app_env="production", **KHOA_THAT, **KHOA_CONG_THAT)
        assert cau_hinh.is_production is True

    def test_gia_tri_mac_dinh_trong_code_van_bi_coi_la_cho_trong(self):
        """Chặn kiểu hỏng tinh vi: ai đó đổi giá trị mặc định mà quên cập nhật danh sách mẫu.

        Các bài trên truyền khoá giả một cách tường minh (để không phụ thuộc biến môi
        trường của CI), nên không bài nào còn kiểm rằng giá trị mặc định ĐANG NẰM TRONG
        CODE thật sự bị nhận diện là chỗ trống. Bài này lấp đúng khe đó.  #Huynh
        """
        for ten in ("secret_key", "jwt_secret_key", "zalopay_key1", "zalopay_key2"):
            mac_dinh = Settings.model_fields[ten].default
            assert mac_dinh in Settings._GIA_TRI_MAU, (
                f"{ten} có giá trị mặc định mới mà chưa thêm vào _GIA_TRI_MAU — "
                "chốt chặn sẽ im lặng cho qua"
            )
