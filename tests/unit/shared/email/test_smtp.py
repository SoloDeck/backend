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
SAI_MAT_KHAU = smtplib.SMTPAuthenticationError(535, b"5.7.8 Username and Password not accepted")


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


class TestFileDinhKem:
    """PDF báo giá / hợp đồng đi kèm thư: vỏ phải là `multipart/mixed` và header nằm ở vỏ ngoài."""

    PDF = b"%PDF-1.4 noi dung gia lap " + bytes([0, 1, 255])

    def _parse(self, **kwargs):  # type: ignore[no-untyped-def]
        from email import message_from_string

        return message_from_string(send_and_capture(**kwargs))

    def test_khong_dinh_kem_thi_vo_thu_van_nhu_cu(self) -> None:
        """Không có tệp thì KHÔNG được bọc thêm `mixed` — thư OTP và thư nhắc giữ nguyên dạng."""
        assert self._parse().get_content_type() == "multipart/alternative"

    def test_dinh_kem_thi_vo_ngoai_la_mixed_va_giu_du_header(self) -> None:
        msg = self._parse(
            from_name="Huỳnh Hoa",
            reply_to="huynhhoa@example.com",
            attachments=[("bao-gia.pdf", self.PDF, "application/pdf")],
        )
        assert msg.get_content_type() == "multipart/mixed"
        assert msg["To"] == "khach@example.com"
        from email.header import decode_header, make_header

        assert str(make_header(decode_header(msg["Subject"]))) == "Về báo giá"
        assert msg["Reply-To"] == "huynhhoa@example.com"
        kinds = [part.get_content_type() for part in msg.get_payload()]
        assert kinds == ["multipart/alternative", "application/pdf"]

    def test_noi_dung_tep_giai_ma_ra_dung_tung_byte(self) -> None:
        msg = self._parse(attachments=[("bao-gia.pdf", self.PDF, "application/pdf")])
        part = msg.get_payload()[1]
        assert part.get_payload(decode=True) == self.PDF
        assert part.get_filename() == "bao-gia.pdf"
        assert part["Content-Disposition"].startswith("attachment")

    def test_ten_tep_co_dau_van_doc_lai_duoc(self) -> None:
        msg = self._parse(attachments=[("báo-giá-đặt-lịch.pdf", self.PDF, "application/pdf")])
        assert msg.get_payload()[1].get_filename() == "báo-giá-đặt-lịch.pdf"

    def test_vua_co_anh_nhung_vua_co_tep_thi_anh_van_nam_trong_khoi_noi_dung(self) -> None:
        """`related` (chữ + ảnh cid) phải nằm TRONG `mixed`, không phải ngang hàng với tệp."""
        msg = self._parse(
            inline_images={"vietqr": bytes([137, 80, 78, 71, 13, 10, 26, 10])},
            attachments=[("hop-dong.pdf", self.PDF, "application/pdf")],
        )
        assert msg.get_content_type() == "multipart/mixed"
        related, pdf = msg.get_payload()
        assert related.get_content_type() == "multipart/related"
        assert [p.get_content_type() for p in related.get_payload()] == [
            "multipart/alternative",
            "image/png",
        ]
        assert pdf.get_content_type() == "application/pdf"


class TestLamSachHeader:
    """Header thư là MỘT dòng: tên và tiêu đề do người dùng gõ không được mang CR/LF vào."""

    def _parse(self, **kwargs):  # type: ignore[no-untyped-def]
        from email import message_from_string

        return message_from_string(send_and_capture(**kwargs))

    def test_tieu_de_co_xuong_dong_thanh_mot_dong_va_khong_sinh_header_la(self) -> None:
        from email.header import decode_header, make_header

        raw = send_and_capture(from_name="Huỳnh Hoa")
        assert "Bcc:" not in raw
        from email import message_from_string

        with patch("smtplib.SMTP") as smtp_cls, patch.object(settings, "smtp_tls", False):
            server = MagicMock()
            smtp_cls.return_value.__enter__.return_value = server
            _send_sync(
                to="khach@example.com",
                subject="Báo giá\r\nBcc: nguoila@example.com",
                html="<p>hi</p>",
                plain="hi",
            )
        msg = message_from_string(server.sendmail.call_args[0][2])
        assert msg["Bcc"] is None
        subject = str(make_header(decode_header(msg["Subject"])))
        assert "\r" not in subject and "\n" not in subject
        assert subject == "Báo giá Bcc: nguoila@example.com"

    def test_ten_nguoi_gui_co_xuong_dong_thanh_mot_dong(self) -> None:
        from email.header import decode_header, make_header

        msg = self._parse(from_name="Đặng Evil\r\nBcc: nguoila@example.com")
        assert msg["Bcc"] is None
        sender = str(make_header(decode_header(msg["From"])))
        assert "\r" not in sender and "\n" not in sender
        assert sender.startswith("Đặng Evil Bcc: nguoila@example.com <")

    def test_reply_to_co_xuong_dong_thanh_mot_dong(self) -> None:
        msg = self._parse(reply_to="a@example.com\r\nBcc: nguoila@example.com")
        assert msg["Bcc"] is None
        assert msg["Reply-To"] == "a@example.com Bcc: nguoila@example.com"

    def test_ten_binh_thuong_khong_bi_dong_vao(self) -> None:
        from email.header import decode_header, make_header

        msg = self._parse(from_name="  Huỳnh   Hoa  ")
        assert str(make_header(decode_header(msg["From"]))).startswith("Huỳnh Hoa <")


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
                smtplib.SMTPRecipientsRefused({"a@b.com": (550, b"5.4.5 sending limit exceeded")}),
                "quota",
            ),
            (smtplib.SMTPConnectError(421, b"cannot connect"), "connect"),
            (smtplib.SMTPServerDisconnected("connection closed"), "connect"),
            (ConnectionRefusedError(111, "Connection refused"), "connect"),
            (TimeoutError("timed out"), "connect"),
            (socket.gaierror("Name or service not known"), "connect"),
            (
                smtplib.SMTPRecipientsRefused(
                    {"khach": (553, b"5.1.3 The recipient address is not a valid RFC 5321 address")}
                ),
                "recipient",
            ),
            # `UnicodeEncodeError` KHÔNG còn tự động là lỗi người nhận — xem `TestLoiMaHoaChuCoDau`.
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


def _loi_ma_hoa_that(hanh_dong) -> UnicodeEncodeError:  # type: ignore[no-untyped-def]
    """Chạy đúng đoạn mã của `smtplib` rồi bắt lấy `UnicodeEncodeError` THẬT.

    Bám vào hành vi thật của thư viện chuẩn (chuỗi nào được đem đi mã hoá, ký tự hỏng nằm ở đâu)
    thay vì tự bịa một ngoại lệ rồi tin rằng nó giống thật. Socket giả để lệnh không đi đâu cả: lỗi
    mã hoá nổ TRƯỚC khi gửi byte nào."""
    smtp = smtplib.SMTP(local_hostname="localhost")
    smtp.sock = MagicMock()
    with pytest.raises(UnicodeEncodeError) as bat:
        hanh_dong(smtp)
    return bat.value


KHACH_CO_DAU = "khách@example.com"


def _rcpt_khach_co_dau(smtp: smtplib.SMTP) -> None:
    smtp.rcpt(KHACH_CO_DAU)


def _mail_from_he_thong_co_dau(smtp: smtplib.SMTP) -> None:
    smtp.mail("hệthống@example.com")


def _auth_mat_khau_co_dau(smtp: smtplib.SMTP) -> None:
    # Mật khẩu ứng dụng Google dán từ trang web hay mang theo dấu cách không ngắt (NBSP).
    smtp.user, smtp.password = "noreply@example.com", "abcd\xa0efgh ijkl mnop"
    smtp.auth("PLAIN", smtp.auth_plain)


def _ehlo_ten_may_co_dau(smtp: smtplib.SMTP) -> None:
    smtp.local_hostname = "Máy-của-Huỳnh"
    smtp.ehlo()


class TestLoiMaHoaChuCoDau:
    """`smtplib` mã hoá MỌI lệnh gửi đi bằng ASCII: EHLO (tên máy), AUTH (tài khoản + mật khẩu),
    MAIL FROM (địa chỉ gửi), RCPT TO (địa chỉ nhận). Chữ có dấu ở bất kỳ chỗ nào đều nổ cùng một
    `UnicodeEncodeError`, nên chỉ lỗi nằm trong địa chỉ NGƯỜI NHẬN mới được bảo "kiểm tra email
    khách". Bảo thế với lỗi mật khẩu hệ thống là chỉ sai đường: sửa email khách bao nhiêu lần
    cũng không hết lỗi."""

    def test_chu_co_dau_trong_dia_chi_nguoi_nhan_la_loi_nguoi_nhan(self) -> None:
        exc = _loi_ma_hoa_that(_rcpt_khach_co_dau)

        reason, message = classify_send_failure(exc, recipient=KHACH_CO_DAU)

        assert reason == "recipient"
        assert "người nhận" in message

    def test_lenh_that_chua_ca_lenh_chu_khong_rieng_dia_chi(self) -> None:
        """Điều kiện tiên quyết của cách nhận diện: `exc.object` là NGUYÊN lệnh, nên so cả chuỗi
        với địa chỉ sẽ không bao giờ khớp — phải xét địa chỉ có chứa ký tự hỏng hay không."""
        exc = _loi_ma_hoa_that(_rcpt_khach_co_dau)

        assert exc.object != KHACH_CO_DAU
        assert KHACH_CO_DAU in exc.object
        assert exc.object[exc.start : exc.end] == "á"

    @pytest.mark.parametrize(
        "hanh_dong",
        [_mail_from_he_thong_co_dau, _auth_mat_khau_co_dau, _ehlo_ten_may_co_dau],
        ids=["dia-chi-gui", "mat-khau-he-thong", "ten-may"],
    )
    def test_chu_co_dau_o_phia_he_thong_khong_bi_do_cho_khach(self, hanh_dong) -> None:  # type: ignore[no-untyped-def]
        exc = _loi_ma_hoa_that(hanh_dong)

        # Khách ĐÚNG địa chỉ ASCII, chẳng có lỗi gì ở họ.
        reason, message = classify_send_failure(exc, recipient="khach@example.com")

        assert reason == "unknown"
        assert "người nhận" not in message

    def test_khong_biet_nguoi_nhan_la_ai_thi_khong_doan(self) -> None:
        exc = _loi_ma_hoa_that(_rcpt_khach_co_dau)

        reason, _ = classify_send_failure(exc)

        assert reason == "unknown"

    def test_dia_chi_khach_trung_dau_nhung_ky_tu_hong_nam_ngoai_dia_chi_thi_khong_tinh(
        self,
    ) -> None:
        """Địa chỉ khách có mặt trong chuỗi, nhưng ký tự hỏng nằm ở chỗ khác của chuỗi."""
        exc = UnicodeEncodeError(
            "ascii", "rcpt TO:<khach@example.com> tên-có-dấu", 28, 29, "ordinal not in range"
        )

        reason, _ = classify_send_failure(exc, recipient="khach@example.com")

        assert reason == "unknown"

    def test_mat_khau_he_thong_tinh_co_chua_dia_chi_khach_van_la_loi_he_thong(self) -> None:
        """Ký tự hỏng ở mật khẩu, không phải ở đoạn trùng với địa chỉ khách."""
        exc = UnicodeEncodeError(
            "ascii", "\0noreply@example.com\0khach@example.com-mật", 40, 41, "ordinal"
        )

        reason, _ = classify_send_failure(exc, recipient="khach@example.com")

        assert reason == "unknown"

    async def test_send_email_gan_nhan_nguoi_nhan_khi_dia_chi_khach_co_dau(self) -> None:
        loi = _loi_ma_hoa_that(_rcpt_khach_co_dau)  # dựng TRƯỚC khi `smtplib.SMTP` bị thay bằng giả
        with (
            patch("smtplib.SMTP") as smtp_cls,
            patch.object(settings, "smtp_tls", False),
            pytest.raises(EmailDeliveryError) as bat,
        ):
            smtp_cls.return_value.__enter__.return_value.sendmail.side_effect = loi
            await send_email(to=KHACH_CO_DAU, subject="s", html="<p>h</p>", plain="h")

        assert bat.value.reason == "recipient"

    async def test_send_email_gan_nhan_unknown_khi_mat_khau_he_thong_co_dau(self) -> None:
        loi = _loi_ma_hoa_that(_auth_mat_khau_co_dau)
        with (
            patch("smtplib.SMTP") as smtp_cls,
            patch.object(settings, "smtp_tls", False),
            patch.object(settings, "smtp_user", "noreply@example.com"),
            patch.object(settings, "smtp_password", "abcd\xa0efgh"),
            pytest.raises(EmailDeliveryError) as bat,
        ):
            smtp_cls.return_value.__enter__.return_value.login.side_effect = loi
            await send_email(to="khach@example.com", subject="s", html="<p>h</p>", plain="h")

        assert bat.value.reason == "unknown"
        assert "người nhận" not in bat.value.message


class TestHopThuKhachDayKhongPhaiHanMucHeThong:
    """`552 5.2.2 ... over quota` là hộp thư của KHÁCH đầy. Marker "quota" trơ trọi từng bắt nhầm nó
    thành "hộp thư hệ thống chạm giới hạn, thử lại sau vài giờ" — lời khuyên sai: thử lại bao nhiêu
    lần thì hộp thư khách vẫn đầy, việc cần làm là báo khách dọn."""

    @pytest.mark.parametrize(
        "ly_do",
        [
            (552, b"5.2.2 The email account that you tried to reach is over quota."),  # Gmail
            (552, b"5.2.2 STOREDRV.Deliver.Exception:QuotaExceededException.MapiExceptionShutoffQuotaExceeded"),  # noqa: E501
            (452, b"4.2.2 Mailbox full"),
            (552, b"Quota exceeded (mailbox for user is full)"),
            (550, b"user is over quota"),
        ],
        ids=["gmail", "exchange", "ma-4.2.2", "dovecot", "chu-tu-do"],
    )
    def test_hop_thu_khach_day_ra_nhom_recipient_voi_cau_rieng(self, ly_do) -> None:  # type: ignore[no-untyped-def]
        exc = smtplib.SMTPRecipientsRefused({"khach@example.com": ly_do})

        reason, message = classify_send_failure(exc)

        assert reason == "recipient"
        assert "đầy" in message
        assert "hệ thống" not in message

    def test_cau_hop_thu_day_khac_cau_dia_chi_sai_va_khac_cau_het_han_muc(self) -> None:
        _, cau_day = classify_send_failure(
            smtplib.SMTPRecipientsRefused({"a@b.com": (552, b"5.2.2 over quota")})
        )
        _, cau_sai_dia_chi = classify_send_failure(
            smtplib.SMTPRecipientsRefused({"a@b.com": (550, b"5.1.1 user unknown")})
        )
        _, cau_het_han_muc = classify_send_failure(
            smtplib.SMTPSenderRefused(550, b"5.4.5 Daily user sending limit exceeded", "a@b.com")
        )
        assert len({cau_day, cau_sai_dia_chi, cau_het_han_muc}) == 3

    @pytest.mark.parametrize(
        "ly_do",
        [
            (550, b"5.4.5 Daily user sending quota exceeded."),  # Gmail, chữ "quota" thay "limit"
            (550, b"5.4.5 Daily user sending limit exceeded"),
            (550, b"Daily sending quota exceeded"),
            (554, b"Message rejected: Daily message quota exceeded"),  # Amazon SES
            (450, b"4.2.1 Rate limit exceeded, try again later"),
            (452, b"4.5.3 Too many messages in this session"),
        ],
        ids=["gmail-quota", "gmail-limit", "khong-ma", "ses", "rate", "qua-nhieu-thu"],
    )
    def test_han_muc_he_thong_ben_trong_RecipientsRefused_van_la_quota(self, ly_do) -> None:  # type: ignore[no-untyped-def]
        """Gmail gói lỗi hết hạn mức gửi vào đúng lớp này — vẫn là chuyện của hộp thư hệ thống,
        và marker của hệ thống phải thắng nhánh người nhận."""
        exc = smtplib.SMTPRecipientsRefused({"khach@example.com": ly_do})

        reason, message = classify_send_failure(exc)

        assert reason == "quota"
        assert "hệ thống" in message

    @pytest.mark.parametrize(
        "exc",
        [
            smtplib.SMTPSenderRefused(550, b"5.4.5 Daily user sending limit exceeded", "a@b.com"),
            smtplib.SMTPDataError(550, b"5.4.5 Daily user sending quota exceeded"),
            smtplib.SMTPDataError(552, b"quota exceeded for this account"),
            smtplib.SMTPSenderRefused(552, b"mailbox over quota", "a@b.com"),
        ],
        ids=["mail-from-limit", "data-quota", "data-quota-tro-trong", "mail-from-over-quota"],
    )
    def test_cac_lop_khac_van_coi_quota_la_han_muc_he_thong(self, exc) -> None:  # type: ignore[no-untyped-def]
        """Lỗi ở MAIL FROM / DATA không phải chuyện của người nhận: hành vi cũ giữ nguyên."""
        assert classify_send_failure(exc)[0] == "quota"

    def test_ten_hop_thu_cua_khach_la_quota_khong_lam_lech_phan_loai(self) -> None:
        """Địa chỉ do khách đặt: một hộp thư tên `quota@...` không được phép kéo lỗi "người dùng
        không tồn tại" thành "hộp thư đầy"."""
        exc = smtplib.SMTPRecipientsRefused({"quota@example.com": (550, b"5.1.1 user unknown")})

        reason, message = classify_send_failure(exc)

        assert reason == "recipient"
        assert "đầy" not in message

    def test_dia_chi_ip_trong_cau_tu_choi_khong_bi_nhan_nham_la_ma_5_4_5(self) -> None:
        exc = smtplib.SMTPRecipientsRefused(
            {"khach@example.com": (550, b"5.7.1 Client host [185.4.5.6] blocked")}
        )

        reason, _ = classify_send_failure(exc)

        assert reason == "recipient"

    async def test_send_email_ra_loi_nguoi_nhan_voi_cau_rieng_khi_hop_thu_khach_day(self) -> None:
        full = smtplib.SMTPRecipientsRefused({"khach@example.com": (552, b"5.2.2 over quota")})
        with (
            patch("smtplib.SMTP", side_effect=full),
            patch.object(settings, "smtp_tls", False),
            pytest.raises(EmailDeliveryError) as bat,
        ):
            await send_email(to="khach@example.com", subject="s", html="<p>h</p>", plain="h")

        assert bat.value.reason == "recipient"
        assert "đầy" in bat.value.message


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
