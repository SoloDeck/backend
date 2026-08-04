"""Header của thư đi — quyết định khách nhìn thấy AI gửi và trả lời về đâu."""

import smtplib
import socket
from unittest.mock import MagicMock, patch

import pytest

from src.config.settings import settings
from src.shared.email.smtp import _send_sync, classify_send_failure, send_email
from src.shared.exceptions.domain import EmailDeliveryError

# Đúng câu Gmail trả về khi App Password bị thu hồi hoặc sai — nghi phạm số một mỗi lần
# hộp thư hệ thống ngừng gửi được.
SAI_MAT_KHAU = smtplib.SMTPAuthenticationError(
    535, b"5.7.8 Username and Password not accepted"
)


def send_and_capture(**kwargs) -> str:  # type: ignore[no-untyped-def]
    """Chạy _send_sync với SMTP giả, trả về nguyên văn thư đã dựng."""
    server = MagicMock()
    with patch("smtplib.SMTP") as smtp_cls, patch.object(settings, "smtp_tls", False):
        smtp_cls.return_value.__enter__.return_value = server
        _send_sync(
            to="khach@example.com", subject="Về báo giá", html="<p>hi</p>", plain="hi", **kwargs
        )
    return server.sendmail.call_args[0][2]


class TestGuiThayMatFreelancer:
    def test_khach_thay_ten_freelancer_chu_khong_phai_solodesk(self) -> None:
        raw = send_and_capture(from_name="Huỳnh Hoa", reply_to="huynhhoa@example.com")
        # Tên hiển thị bị mã hoá base64 vì có dấu tiếng Việt — giải ra để kiểm tra.
        from email import message_from_string
        from email.header import decode_header, make_header

        sender = str(make_header(decode_header(message_from_string(raw)["From"])))
        assert sender.startswith("Huỳnh Hoa <")
        assert settings.smtp_from_name not in sender

    def test_dia_chi_gui_van_la_cua_solodesk(self) -> None:
        """KHÔNG được khai địa chỉ freelancer: hộp thư đi là của SoloDesk, khai địa chỉ
        người khác thì Gmail ghi đè và máy chủ khách trượt SPF → thư vào spam."""
        from email import message_from_string

        msg = message_from_string(
            send_and_capture(from_name="Huỳnh Hoa", reply_to="huynhhoa@example.com")
        )
        assert msg["Reply-To"] == "huynhhoa@example.com"
        assert "huynhhoa@example.com" not in (msg["From"] or "")

    def test_dia_chi_email_khong_bi_ma_hoa_cung_ten_co_dau(self) -> None:
        """Ghép chuỗi f-string thì Python mã hoá NGUYÊN header, kể cả `<a@b.com>` →
        `=3Ca=40b=2Ecom=3E`. Sai RFC 2047, máy chủ thư có quyền từ chối. Chỉ tên mới
        được mã hoá."""
        raw = send_and_capture(from_name="Huỳnh Hoa")
        from_line = next(line for line in raw.splitlines() if line.startswith("From:"))
        assert f"<{settings.smtp_from_email}>" in from_line, from_line
        assert "=3C" not in from_line and "=40" not in from_line

    def test_khong_truyen_gi_thi_van_la_thu_he_thong(self) -> None:
        """Thư OTP đăng nhập vẫn phải mang danh SoloDesk như trước."""
        from email import message_from_string

        msg = message_from_string(send_and_capture())
        assert settings.smtp_from_name in msg["From"]
        assert msg["Reply-To"] is None

    def test_ten_rong_thi_lui_ve_ten_he_thong(self) -> None:
        from email import message_from_string

        msg = message_from_string(send_and_capture(from_name="   "))
        assert settings.smtp_from_name in msg["From"]


class TestHetGioCho:
    """`smtplib` mặc định KHÔNG có timeout — máy chủ thư im lặng là treo cỡ 2 phút."""

    def test_truyen_timeout_khi_dung_starttls(self) -> None:
        with patch("smtplib.SMTP") as smtp_cls, patch.object(settings, "smtp_tls", False):
            _send_sync(to="a@b.com", subject="s", html="<p>h</p>", plain="h")
        smtp_cls.assert_called_once_with(
            settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout_seconds
        )

    def test_truyen_timeout_khi_dung_ssl(self) -> None:
        """Nhánh SSL (cổng 465) cũng phải có timeout — đây là đường lui khi 587 bị chặn,
        tức đúng lúc mạng đang có vấn đề, càng không được để nó treo."""
        with patch("smtplib.SMTP_SSL") as smtp_cls, patch.object(settings, "smtp_tls", True):
            _send_sync(to="a@b.com", subject="s", html="<p>h</p>", plain="h")
        smtp_cls.assert_called_once_with(
            settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout_seconds
        )

    def test_timeout_nho_hon_muc_axios_bo_cuoc(self) -> None:
        """Web bỏ cuộc ở 15 giây (`web/src/configs/axios.ts`). Backend không trả lời trước
        mốc đó thì mọi lỗi SMTP đều hiện thành "mất mạng", và toàn bộ phần phân loại lỗi
        bên dưới thành vô dụng vì câu trả lời không bao giờ về kịp."""
        assert settings.smtp_timeout_seconds < 15


class TestPhanLoaiLoiGui:
    """Ba nhóm lỗi cần ba lời khuyên khác nhau, không phải một câu 'thử lại sau'."""

    @pytest.mark.parametrize(
        ("exc", "mong_doi"),
        [
            (SAI_MAT_KHAU, "auth"),
            (
                smtplib.SMTPSenderRefused(
                    550, b"5.4.5 Daily user sending limit exceeded", "a@b.com"
                ),
                "quota",
            ),
            (
                smtplib.SMTPRecipientsRefused(
                    {"a@b.com": (550, b"5.4.5 sending limit exceeded")}
                ),
                "quota",
            ),
            (smtplib.SMTPConnectError(421, b"cannot connect"), "connect"),
            (smtplib.SMTPServerDisconnected("connection closed"), "connect"),
            (ConnectionRefusedError(111, "Connection refused"), "connect"),
            (TimeoutError("timed out"), "connect"),
            (socket.gaierror("Name or service not known"), "connect"),
            (smtplib.SMTPDataError(554, b"transaction failed"), "unknown"),
            (ValueError("chuyện gì đó khác hẳn"), "unknown"),
        ],
    )
    def test_xep_dung_nhom(self, exc: BaseException, mong_doi: str) -> None:
        reason, message = classify_send_failure(exc)
        assert reason == mong_doi
        assert message.strip()

    def test_sai_mat_khau_khong_bi_gan_nham_thanh_loi_mang(self) -> None:
        """Chốt chặn cho thứ tự trong `classify_send_failure`.

        `smtplib.SMTPException` KẾ THỪA `OSError`. Xét nhánh mạng trước thì sai mật khẩu bị
        gán thành "không kết nối được" → người dùng được khuyên thử lại, trong khi thử lại
        một nghìn lần cũng vậy. Đảo thứ tự hai nhánh đó là test này phải ĐỎ."""
        assert isinstance(smtplib.SMTPException(), OSError)  # tiền đề của bài test
        reason, _ = classify_send_failure(SAI_MAT_KHAU)
        assert reason == "auth"

    def test_auth_va_quota_khuyen_hai_viec_khac_nhau(self) -> None:
        """Cả điểm của lần sửa này: hai câu KHÔNG được giống nhau."""
        _, cau_auth = classify_send_failure(SAI_MAT_KHAU)
        _, cau_quota = classify_send_failure(
            smtplib.SMTPSenderRefused(550, b"5.4.5 daily user sending limit", "a@b.com")
        )
        assert cau_auth != cau_quota


class TestSendEmailNemLoiCoTen:
    async def test_nem_loi_co_ten_kem_reason(self) -> None:
        with (
            patch("smtplib.SMTP", side_effect=ConnectionRefusedError(111, "refused")),
            patch.object(settings, "smtp_tls", False),
            pytest.raises(EmailDeliveryError) as bat,
        ):
            await send_email(to="a@b.com", subject="s", html="<p>h</p>", plain="h")
        assert bat.value.reason == "connect"

    async def test_giu_loi_goc_lam_nguyen_nhan(self) -> None:
        """`raise ... from exc` — mất lỗi gốc là mất luôn khả năng truy nguyên."""
        with (
            patch("smtplib.SMTP", side_effect=SAI_MAT_KHAU),
            patch.object(settings, "smtp_tls", False),
            pytest.raises(EmailDeliveryError) as bat,
        ):
            await send_email(to="a@b.com", subject="s", html="<p>h</p>", plain="h")
        assert bat.value.__cause__ is SAI_MAT_KHAU
        assert bat.value.reason == "auth"

    async def test_cau_cho_nguoi_dung_khong_lo_host_hay_tai_khoan(self) -> None:
        """Người dùng cuối không làm gì được với tên host, còn kẻ dò thì có."""
        with (
            patch("smtplib.SMTP", side_effect=ConnectionRefusedError(111, "refused")),
            patch.object(settings, "smtp_tls", False),
            pytest.raises(EmailDeliveryError) as bat,
        ):
            await send_email(to="a@b.com", subject="s", html="<p>h</p>", plain="h")
        cau = bat.value.message
        assert settings.smtp_host not in cau
        assert not settings.smtp_user or settings.smtp_user not in cau
