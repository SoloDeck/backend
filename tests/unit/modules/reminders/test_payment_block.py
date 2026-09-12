"""Khối thanh toán trong thư nhắc — chuỗi VietQR và phần chữ đi kèm.

Đây là chỗ SAI THÌ MẤT TIỀN THẬT: chuỗi QR sai một ký tự thì app ngân hàng hoặc từ chối
quét, hoặc tệ hơn là điền sai số tài khoản. Mà lỗi đó không hiện ra ở đâu cho tới lúc khách
đứng quét thật. Nên bộ này giải mã ngược lại chuỗi để đối chiếu, không chỉ kiểm "có sinh ra
chuỗi nào đó".  #Huynh
"""

import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from src.modules.reminders.application.attachments import (
    ALLOWED_IMAGE_TYPES,
    images_html,
    parse_attachments,
    validate_image,
)
from src.modules.reminders.application.payment_block import (
    PaymentInfo,
    build_payment_block,
    build_payment_section,
    crc16_ccitt,
    resolve_amount_and_memo,
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


# ---------------------------------------------------------------------------
# Số tiền in vào mã QR khi lời nhắc trỏ vào một DỰ ÁN
# ---------------------------------------------------------------------------

_DEAL = uuid.uuid4()
_DEAL_KHAC = uuid.uuid4()


def _moc(deal_id: uuid.UUID, label: str, amount: int, collected: bool) -> dict:
    """Một dòng y như `AnalyticsRepository.milestone_rows` trả về: MỖI TASK MỘT DÒNG."""
    return {
        "deal_id": deal_id,
        "client_id": uuid.uuid4(),
        "client_name": "Công ty ABC",
        "label": label,
        "amount": Decimal(amount),
        "collected": collected,
    }


def _nhac_du_an() -> SimpleNamespace:
    return SimpleNamespace(
        target_type="deal",
        target_id=_DEAL,
        owner_user_id=uuid.uuid4(),
        reminder_type="payment_due",
    )


def _gia_lap_moc(rows: list[dict]):
    """Thay kho dữ liệu mốc bằng danh sách dựng sẵn — bài này không cần DB."""
    return patch(
        "src.modules.analytics.infrastructure.repository.AnalyticsRepository",
        return_value=SimpleNamespace(milestone_rows=AsyncMock(return_value=rows)),
    )


class TestSoTienNhacTheoDuAn:
    """Nhắc thanh toán cho một DỰ ÁN: QR phải mang TỔNG các mốc chưa thu."""

    async def test_cong_het_cac_moc_chua_thu_chu_khong_dung_o_moc_dau(self) -> None:
        # Bản cũ gọi một hàm không tồn tại rồi `return` ngay ở dòng đầu khớp deal: vừa nổ
        # AttributeError (QR trống số tiền), vừa bỏ sót các mốc sau.  #Huynh
        rows = [
            _moc(_DEAL, "Đợt 1", 2_000_000, collected=True),
            _moc(_DEAL, "Đợt 2", 5_000_000, collected=False),
            _moc(_DEAL, "Đợt 3", 3_000_000, collected=False),
        ]
        with _gia_lap_moc(rows):
            amount, memo = await resolve_amount_and_memo(object(), _nhac_du_an(), "Dự án X")

        assert amount == Decimal(8_000_000)
        assert memo == "Dự án X"

    async def test_khong_tinh_nham_moc_cua_du_an_khac(self) -> None:
        rows = [
            _moc(_DEAL_KHAC, "Đợt 1 dự án khác", 99_000_000, collected=False),
            _moc(_DEAL, "Đợt 1", 4_000_000, collected=False),
        ]
        with _gia_lap_moc(rows):
            amount, _ = await resolve_amount_and_memo(object(), _nhac_du_an(), "Dự án X")

        assert amount == Decimal(4_000_000)

    async def test_thu_du_roi_thi_khong_gan_so_tien_vao_qr(self) -> None:
        # Gắn số tiền 0 vào QR là khách quét ra ô "0 đ" — thà để khách tự nhập.
        rows = [_moc(_DEAL, "Đợt 1", 4_000_000, collected=True)]
        with _gia_lap_moc(rows):
            amount, _ = await resolve_amount_and_memo(object(), _nhac_du_an(), "Dự án X")

        assert amount is None

    async def test_du_an_chua_co_moc_nao_thi_khong_co_so_tien(self) -> None:
        with _gia_lap_moc([]):
            amount, memo = await resolve_amount_and_memo(object(), _nhac_du_an(), "Dự án X")

        assert amount is None
        assert memo == "Dự án X"

    async def test_so_tien_thuc_su_duoc_in_vao_ma_qr(self) -> None:
        # Đi hết đường: tra tiền → dựng khối → chuỗi VietQR phải mang đúng số tiền.
        owner = SimpleNamespace(
            bank_code="970436",
            bank_account_number="1027123456",
            bank_account_holder="NGUYEN VAN A",
            momo_phone_number=None,
            bank_account_info=None,
        )
        rows = [
            _moc(_DEAL, "Đợt 1", 5_000_000, collected=False),
            _moc(_DEAL, "Đợt 2", 3_000_000, collected=False),
        ]
        with _gia_lap_moc(rows):
            html, plain, _ = await build_payment_section(object(), _nhac_du_an(), owner, "Dự án X")

        assert "8.000.000 ₫" in html
        assert "8.000.000 ₫" in plain


class TestLoiTraTienKhongBiNuotAmTham:
    """`except Exception` ở đây từng giấu lỗi gọi nhầm tên hàm suốt nhiều lần chạy thật."""

    _OWNER = SimpleNamespace(
        bank_code="970436",
        bank_account_number="1027123456",
        bank_account_holder="NGUYEN VAN A",
        momo_phone_number=None,
        bank_account_info=None,
    )

    async def test_loi_lap_trinh_phai_no_ra_chu_khong_gui_qr_trong(self) -> None:
        with (
            patch(
                "src.modules.reminders.application.payment_block.resolve_amount_and_memo",
                AsyncMock(side_effect=AttributeError("gọi nhầm tên hàm")),
            ),
            pytest.raises(AttributeError),
        ):
            await build_payment_section(object(), _nhac_du_an(), self._OWNER, "Dự án X")

    async def test_db_truc_trac_thi_thu_van_di_kem_so_tai_khoan(self) -> None:
        # Mất số tiền chỉ là bất tiện; không gửi được thư mới là mất tiền thật.
        with patch(
            "src.modules.reminders.application.payment_block.resolve_amount_and_memo",
            AsyncMock(side_effect=SQLAlchemyError("DB trục trặc")),
        ):
            html, plain, _ = await build_payment_section(
                object(), _nhac_du_an(), self._OWNER, "Dự án X"
            )

        assert "1027123456" in html
        assert "1027123456" in plain
        assert "₫" not in html
