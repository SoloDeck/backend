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

    def test_production_chan_khoa_sandbox_cua_cong_thanh_toan(self):
        # Khoá sandbox ZaloPay/MoMo là công khai — ai đọc tài liệu của cổng cũng có,
        # nên dùng ở production là tự mở đường cho người ngoài giả callback nâng gói.
        with pytest.raises(ValidationError) as loi:
            _dung(app_env="production", **KHOA_THAT)
        assert "ZALOPAY_KEY1" in str(loi.value)

    def test_staging_van_dung_duoc_khoa_sandbox_cua_cong(self):
        # Cố ý nới ở staging: ci.yml hiện KHÔNG truyền ZALOPAY_KEY1/KEY2 cho môi trường
        # nào, nên chặn ở đây là staging chết ngay lần merge tới mà chẳng được gì —
        # staging vốn chỉ cần cổng sandbox.
        assert _dung(app_env="staging", **KHOA_THAT).app_env == "staging"

    def test_production_du_khoa_that_thi_qua(self):
        cau_hinh = _dung(app_env="production", **KHOA_THAT, **KHOA_CONG_THAT)
        assert cau_hinh.is_production is True
