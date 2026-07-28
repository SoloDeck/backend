"""Khối thanh toán trong thư nhắc — chuỗi VietQR và phần chữ đi kèm.

Đây là chỗ SAI THÌ MẤT TIỀN THẬT: chuỗi QR sai một ký tự thì app ngân hàng hoặc từ chối
quét, hoặc tệ hơn là điền sai số tài khoản. Mà lỗi đó không hiện ra ở đâu cho tới lúc khách
đứng quét thật. Nên bộ này giải mã ngược lại chuỗi để đối chiếu, không chỉ kiểm "có sinh ra
chuỗi nào đó".  #Huynh
"""

from decimal import Decimal

import pytest

from src.modules.reminders.application.attachments import (
    ALLOWED_IMAGE_TYPES,
    images_html,
    parse_attachments,
    validate_image,
)
from src.modules.reminders.application.payment_block import (
    PaymentInfo,
    build_payment_block,
    crc16_ccitt,
    vietqr_payload,
)
from src.shared.exceptions.domain import ValidationError

_INFO = PaymentInfo(
    bank_code="970436",
    bank_name="Vietcombank (VCB)",
    account_number="1027123456",
    account_holder="NGUYEN VAN A",
)


def _parse_emv(payload: str) -> dict[str, str]:
    """Bóc chuỗi EMVCo thành {mã: giá trị} — đọc ngược đúng cách app ngân hàng đọc."""
    out: dict[str, str] = {}
    i = 0
    while i < len(payload):
        tag = payload[i : i + 2]
        length = int(payload[i + 2 : i + 4])
        out[tag] = payload[i + 4 : i + 4 + length]
        i += 4 + length
    return out


class TestChuoiVietQR:
    def test_giai_ma_lai_ra_dung_ngan_hang_va_so_tai_khoan(self) -> None:
        payload = vietqr_payload(bank_code="970436", account_number="1027123456")
        fields = _parse_emv(payload)

        merchant = _parse_emv(fields["38"])
        assert merchant["00"] == "A000000727"  # NAPAS
        account = _parse_emv(merchant["01"])
        assert account["00"] == "970436"
        assert account["01"] == "1027123456"
        assert fields["53"] == "704"  # VND
        assert fields["58"] == "VN"

    def test_co_so_tien_va_noi_dung_thi_dien_san(self) -> None:
        payload = vietqr_payload(
            bank_code="970436",
            account_number="1027123456",
            amount=Decimal(9_420_000),
            memo="INV-2026-0042",
        )
        fields = _parse_emv(payload)
        assert fields["54"] == "9420000"
        assert _parse_emv(fields["62"])["08"] == "INV-2026-0042"
        # QR có số tiền là loại "dùng một lần".
        assert fields["01"] == "12"

    def test_khong_co_so_tien_thi_van_hop_le(self) -> None:
        fields = _parse_emv(vietqr_payload(bank_code="970436", account_number="1027123456"))
        assert "54" not in fields
        assert fields["01"] == "11"

    def test_crc_dung_chuan_va_nam_cuoi_chuoi(self) -> None:
        payload = vietqr_payload(bank_code="970436", account_number="1027123456")
        body, crc = payload[:-4], payload[-4:]
        assert body.endswith("6304")
        assert crc16_ccitt(body) == crc
        # Vector chuẩn của CRC-16/CCITT-FALSE — chốt lại thuật toán, không chỉ chốt tính nhất quán.
        assert crc16_ccitt("123456789") == "29B1"

    def test_noi_dung_qua_dai_bi_cat_cho_vua_gioi_han_ngan_hang(self) -> None:
        fields = _parse_emv(
            vietqr_payload(bank_code="970436", account_number="1027123456", memo="x" * 60)
        )
        assert len(_parse_emv(fields["62"])["08"]) == 25


class TestKhoiThanhToan:
    def test_du_thong_tin_thi_co_qr_va_du_dong_chu(self) -> None:
        html, plain, qr = build_payment_block(
            _INFO, amount=Decimal(9_420_000), memo="INV-2026-0042"
        )
        assert qr is not None and qr[:8] == b"\x89PNG\r\n\x1a\n"  # đúng là ảnh PNG
        for expected in ("Vietcombank (VCB)", "1027123456", "NGUYEN VAN A", "INV-2026-0042"):
            assert expected in html
            assert expected in plain
        assert "9.420.000 ₫" in html
        # Phần chữ LUÔN có: rất nhiều trình đọc mail chặn ảnh theo mặc định.
        assert "Số tài khoản" in plain

    def test_chua_khai_ngan_hang_thi_khong_QR_nhung_con_momo(self) -> None:
        html, plain, qr = build_payment_block(PaymentInfo(momo_phone="0901234567"))
        assert qr is None
        assert "0901234567" in html and "0901234567" in plain

    def test_chua_khai_gi_thi_tra_rong_khong_chen_khung_trong(self) -> None:
        html, plain, qr = build_payment_block(PaymentInfo())
        assert (html, plain, qr) == ("", "", None)

    def test_escape_chong_chen_the(self) -> None:
        html, _, _ = build_payment_block(
            PaymentInfo(
                bank_code="970436",
                bank_name="<script>alert(1)</script>",
                account_number="1027123456",
            )
        )
        assert "<script>" not in html
        assert "&lt;script&gt;" in html


# ---------------------------------------------------------------------------
# Ảnh freelancer chèn vào thư
# ---------------------------------------------------------------------------

class TestAnhChenVaoThu:
    """Freelancer chèn mã QR chụp sẵn / ảnh sản phẩm vào thư nhắc."""

    def test_chi_nhan_anh_video_thi_bao_ro_phai_dan_link(self) -> None:
        # Email KHÔNG phát được video. Từ chối thẳng và nói cách khác thay vì im lặng gửi
        # một cục tải về mà khách không mở.
        with pytest.raises(ValidationError, match="dán link"):
            validate_image(content_type="video/mp4", data=b"x")

    def test_anh_hop_le_thi_qua(self) -> None:
        for content_type in ALLOWED_IMAGE_TYPES:
            validate_image(content_type=content_type, data=b"x")

    def test_anh_qua_lon_bi_chan(self) -> None:
        with pytest.raises(ValidationError, match="quá lớn"):
            validate_image(content_type="image/png", data=b"x" * (11 * 1024 * 1024))

    def test_ban_ghi_hong_trong_DB_thi_bo_qua_khong_no(self) -> None:
        images = parse_attachments([{"key": "a.png"}, {"khong_co_key": 1}, "rác", None])
        assert [i.key for i in images] == ["a.png"]

    def test_dung_cid_de_hien_trong_than_thu(self) -> None:
        images = parse_attachments([{"key": "a.png", "filename": "qr.png"}])
        html = images_html(images, {"img0": "cid:img0"})
        assert 'src="cid:img0"' in html
        assert 'alt="qr.png"' in html

    def test_anh_tai_khong_ve_thi_khong_chen_the_rong(self) -> None:
        images = parse_attachments([{"key": "a.png"}])
        assert images_html(images, {}) == ""
