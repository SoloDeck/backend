"""Header của thư đi — quyết định khách nhìn thấy AI gửi và trả lời về đâu."""

from unittest.mock import MagicMock, patch

from src.config.settings import settings
from src.shared.email.smtp import _send_sync


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
