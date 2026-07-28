"""Khâu GỬI lời nhắc — phần từng là `raise NotImplementedError`.

Tin nhắc đi THẲNG tới khách hàng thật, nên những thứ được phủ ở đây không phải chuyện
hình thức: gửi trùng, gửi thư trắng, và retry mù khi khách còn chưa có email.
"""

import smtplib
import uuid
from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.modules.reminders.application import delivery_service as _delivery_mod
from src.modules.reminders.application.delivery_service import (
    MAX_DELIVERY_ATTEMPTS,
    ReminderDeliveryService,
    build_body,
    build_footer,
    build_subject,
    is_retryable_smtp_error,
)
from src.shared.exceptions.domain import NotFoundError


@pytest.fixture
def notifications() -> Iterator[MagicMock]:
    """Chặn NotificationService để soi xem có bắn thông báo hay không.

    Service dựng nó ngay trong hàm (`NotificationService(db=self.db)`) nên phải patch tại
    chỗ nó được nhìn thấy, tức module delivery_service.
    """
    with patch("src.modules.reminders.application.delivery_service.NotificationService") as cls:
        instance = cls.return_value
        instance.notify_reminder_sent = AsyncMock()
        instance.notify_reminder_due = AsyncMock()
        instance.notify_reminder_failed = AsyncMock()
        yield instance


def make_reminder(**overrides):  # type: ignore[no-untyped-def]
    reminder = MagicMock()
    reminder.id = overrides.get("id", uuid.uuid4())
    reminder.owner_user_id = overrides.get("owner_user_id", uuid.uuid4())
    reminder.target_type = overrides.get("target_type", "deal")
    reminder.target_id = overrides.get("target_id", uuid.uuid4())
    reminder.reminder_type = overrides.get("reminder_type", "follow_up")
    reminder.channel = overrides.get("channel", "email")
    reminder.status = overrides.get("status", "pending")
    reminder.message_preview = overrides.get("message_preview", "Chào anh, em xin hỏi thăm ạ.")
    reminder.retry_count = overrides.get("retry_count", 0)
    # Khai TƯỜNG MINH: `MagicMock` tự sinh thuộc tính, để trống thì `attachments` thành một
    # mock chứ không phải danh sách rỗng — test sẽ chạy khác hẳn lúc chạy thật.
    reminder.attachments = overrides.get("attachments", [])
    return reminder


def make_client(name: str = "Quán cà phê Nắng", email: str | None = "khach@example.com"):  # type: ignore[no-untyped-def]
    client = MagicMock()
    client.name = name
    client.email = email
    return client


def make_owner(**overrides):  # type: ignore[no-untyped-def]
    """Chủ deal. Các trường nhận tiền phải khai TƯỜNG MINH: `MagicMock` tự sinh thuộc tính
    cho mọi tên, nên bỏ trống là khối thanh toán tưởng đã có số tài khoản và đi dựng mã QR
    từ một object mock.  #Huynh"""
    owner = MagicMock()
    owner.full_name = overrides.get("full_name", "Huỳnh Hoa")
    owner.email = overrides.get("email", "huynhhoa@example.com")
    owner.bank_code = overrides.get("bank_code")
    owner.bank_account_number = overrides.get("bank_account_number")
    owner.bank_account_holder = overrides.get("bank_account_holder")
    owner.momo_phone_number = overrides.get("momo_phone_number")
    owner.bank_account_info = overrides.get("bank_account_info")
    return owner


def make_db():  # type: ignore[no-untyped-def]
    """Session giả. `add()` phải là MagicMock — AsyncMock biến nó thành coroutine không
    ai await, pytest báo `PytestUnraisableExceptionWarning` mà không nói rõ vì sao."""
    db = AsyncMock()
    db.add = MagicMock()
    return db


def make_service(reminder, client=None, label="Thiết kế logo", send_email=None, owner=None):  # type: ignore[no-untyped-def]
    repo = AsyncMock()
    repo.get_for_delivery.return_value = reminder
    repo.resolve_target.return_value = (client if client is not None else make_client(), label)
    owner = owner if owner is not None else make_owner()
    repo.get_owner.return_value = owner
    return (
        ReminderDeliveryService(
            db=make_db(),
            send_email=send_email or AsyncMock(),
            repo=repo,
        ),
        repo,
    )


class TestSoanNoiDung:
    def test_tieu_de_co_ten_du_an_thi_dung_ten_du_an(self) -> None:
        assert build_subject("proposal_follow_up", "Thiết kế logo") == "Về báo giá Thiết kế logo"

    def test_khong_co_ten_du_an_van_ra_tieu_de_doc_duoc(self) -> None:
        """Khách chưa gắn với deal nào — không được ra "Về báo giá " cụt lủn."""
        assert build_subject("proposal_follow_up", None) == "Về báo giá đã gửi"
        assert build_subject("payment_overdue", "  ") == "Hoá đơn đã quá hạn thanh toán"

    def test_tieu_de_khong_gan_tien_to_solodesk(self) -> None:
        """Thư này là freelancer nhắn cho khách, không phải hệ thống thông báo."""
        assert "SoloDesk" not in build_subject("follow_up", "Website bán hàng")

    def test_loai_nhac_la_thi_van_co_tieu_de(self) -> None:
        assert build_subject("khong_ton_tai", "Dự án X") == "Về Dự án X"

    def test_escape_html_trong_noi_dung_khach_gui(self) -> None:
        """Chỉ một dấu `&` hay `<` là vỡ HTML của thư gửi khách."""
        html, plain = build_body("Giá < 5tr & còn thương lượng", "Huỳnh Hoa")
        assert "&lt; 5tr &amp;" in html
        assert "<p>Giá" in html
        # Bản plain giữ nguyên chữ người dùng gõ, không escape.
        assert "Giá < 5tr & còn thương lượng" in plain

    def test_dong_trong_tach_thanh_doan_rieng(self) -> None:
        html, _ = build_body("Chào anh,\n\nEm gửi báo giá ạ.", "Huỳnh Hoa")
        assert html.count("<p>") == 3  # 2 đoạn + chữ ký

    def test_xuong_dong_don_giu_lai_bang_br(self) -> None:
        html, _ = build_body("Dòng một\nDòng hai", None)
        assert "<br>" in html

    def test_ky_ten_bang_ten_freelancer(self) -> None:
        html, plain = build_body("Chào anh", "Huỳnh Hoa")
        assert "Huỳnh Hoa" in html
        # Chữ ký đứng ngay sau nội dung, trước chân thư.
        assert "Chào anh\n\n—\nHuỳnh Hoa" in plain

    def test_khong_co_ten_thi_khong_ky_trong(self) -> None:
        html, plain = build_body("Chào anh", None)
        assert "—" not in html
        assert plain == "Chào anh"


class TestChanThu:
    """`From` buộc phải là hộp thư SoloDesk, nên khách chỉ thấy `solodeskai@gmail.com`
    và không biết đó là ai. Chân thư bù đúng chỗ đó."""

    def test_khach_biet_ai_gui_va_co_email_that_de_luu(self) -> None:
        footer = build_footer("Huỳnh Hoa", "huynhhoa@example.com", "Thiết kế logo")
        assert "Huỳnh Hoa (huynhhoa@example.com)" in footer
        assert "Thiết kế logo" in footer
        assert "về thẳng hộp thư của Huỳnh Hoa" in footer

    def test_khong_co_du_an_thi_bo_dong_do_chu_khong_de_trong(self) -> None:
        footer = build_footer("Huỳnh Hoa", "huynhhoa@example.com", None)
        assert "Về dự án" not in footer
        assert "Huỳnh Hoa (huynhhoa@example.com)" in footer

    def test_khong_biet_nguoi_gui_thi_khong_chan_thu(self) -> None:
        """Thà không có chân thư còn hơn có một cái ghi "gửi từ  ()"."""
        assert build_footer(None, None, "Dự án X") == ""

    def test_chan_thu_duoc_escape_va_gan_vao_ca_html_lan_text(self) -> None:
        html, plain = build_body(
            "Chào anh", "Huỳnh Hoa", "huynhhoa@example.com", "Logo <Quán> & Cà phê"
        )
        assert "Logo &lt;Quán&gt; &amp; Cà phê" in html
        assert "<hr" in html
        assert "Logo <Quán> & Cà phê" in plain
        assert "huynhhoa@example.com" in plain


class TestPhanLoaiLoiSmtp:
    def test_dia_chi_bi_tu_choi_thi_khong_thu_lai(self) -> None:
        """Thử mười lần cũng thế — báo ngay còn hơn bắt người dùng đợi ba lượt retry."""
        assert is_retryable_smtp_error(smtplib.SMTPRecipientsRefused({})) is False

    def test_sai_mat_khau_ung_dung_thi_khong_thu_lai(self) -> None:
        assert is_retryable_smtp_error(smtplib.SMTPAuthenticationError(535, b"nope")) is False

    def test_mat_ket_noi_thi_dang_thu_lai(self) -> None:
        assert is_retryable_smtp_error(smtplib.SMTPServerDisconnected("bye")) is True
        assert is_retryable_smtp_error(TimeoutError("mạng chậm")) is True


class TestChanGuiTrung:
    async def test_reminder_da_gui_thi_khong_gui_lai(self) -> None:
        """Chốt chặn quan trọng nhất: worker và nút "Gửi ngay" bấm trùng nhau."""
        send_email = AsyncMock()
        service, _ = make_service(make_reminder(status="sent"), send_email=send_email)

        result = await service.deliver(uuid.uuid4())

        assert result.status == "sent"
        assert result.delivered is False
        send_email.assert_not_awaited()

    async def test_reminder_da_huy_thi_khong_gui(self) -> None:
        send_email = AsyncMock()
        service, _ = make_service(make_reminder(status="cancelled"), send_email=send_email)

        result = await service.deliver(uuid.uuid4())

        assert result.status == "cancelled"
        send_email.assert_not_awaited()

    async def test_khong_tim_thay_reminder_thi_bao_404(self) -> None:
        service, repo = make_service(make_reminder())
        repo.get_for_delivery.return_value = None

        with pytest.raises(NotFoundError):
            await service.deliver(uuid.uuid4())


class TestKenhEmail:
    async def test_gui_email_cho_khach_va_danh_dau_da_gui(self) -> None:
        send_email = AsyncMock()
        reminder = make_reminder(channel="email")
        service, repo = make_service(reminder, send_email=send_email)

        result = await service.deliver(reminder.id)

        send_email.assert_awaited_once()
        assert send_email.await_args.kwargs["to"] == "khach@example.com"
        assert send_email.await_args.kwargs["subject"] == "Hỏi thăm về Thiết kế logo"
        assert reminder.status == "sent"
        assert result.delivered is True
        repo.add_delivery_record.assert_awaited_once()
        assert repo.add_delivery_record.await_args.kwargs["outcome"] == "success"

    async def test_khach_thay_ten_freelancer_va_tra_loi_ve_freelancer(self) -> None:
        """Thư là freelancer nhắn cho khách của họ, SoloDesk chỉ soạn và bấm gửi hộ.

        Không đặt được ĐỊA CHỈ của freelancer vào From (hộp thư đi là của SoloDesk, khai
        địa chỉ người khác là trượt SPF → vào spam), nên danh tính đi bằng tên hiển thị
        và Reply-To.
        """
        send_email = AsyncMock()
        reminder = make_reminder(channel="email")
        service, _ = make_service(reminder, send_email=send_email)

        await service.deliver(reminder.id)

        kwargs = send_email.await_args.kwargs
        assert kwargs["from_name"] == "Huỳnh Hoa"
        assert kwargs["reply_to"] == "huynhhoa@example.com"

    async def test_khach_chua_co_email_thi_hong_ngay_khong_retry(self) -> None:
        """Retry mù ở đây là bắt người dùng đợi ba lượt để biết một chuyện tự sửa được."""
        send_email = AsyncMock()
        reminder = make_reminder(channel="email")
        service, repo = make_service(
            reminder, client=make_client(email=None), send_email=send_email
        )

        result = await service.deliver(reminder.id)

        send_email.assert_not_awaited()
        assert result.status == "failed"
        assert result.should_retry is False
        assert "chưa có email" in result.detail
        assert reminder.retry_count == 0

    async def test_noi_dung_rong_thi_khong_gui_thu_trang(self) -> None:
        send_email = AsyncMock()
        reminder = make_reminder(channel="email", message_preview="   ")
        service, _ = make_service(reminder, send_email=send_email)

        result = await service.deliver(reminder.id)

        send_email.assert_not_awaited()
        assert result.status == "failed"
        assert "chưa có nội dung" in result.detail

    async def test_khong_tim_thay_khach_thi_bao_ro(self) -> None:
        reminder = make_reminder(channel="email")
        service, repo = make_service(reminder)
        repo.resolve_target.return_value = (None, None)

        result = await service.deliver(reminder.id)

        assert result.status == "failed"
        assert "Không tìm thấy khách hàng" in result.detail


class TestKhoiThanhToanTrongThu:
    """Thư nhắc TIỀN phải nói được khách chuyển vào đâu (Phiếu SU26SE083, dòng 140).

    Trước đây thư chỉ có nội dung + chữ ký, khách đọc xong phải nhắn hỏi lại số tài khoản —
    đúng cái ma sát phiếu muốn xoá.  #Huynh
    """

    _OWNER = dict(
        bank_code="970436",
        bank_account_number="1027123456",
        bank_account_holder="NGUYEN VAN A",
    )

    @staticmethod
    def _fixed_amount():  # type: ignore[no-untyped-def]
        """Chốt số tiền lại để bài này chỉ kiểm CHUYỆN CHÈN KHỐI.

        Việc suy ra số tiền (hoá đơn còn nợ / mốc chưa thu) đụng DB thật, đã có bài riêng ở
        tầng tích hợp; nhét nó vào đây thì test hỏng vì lý do chẳng liên quan.  #Huynh
        """
        from decimal import Decimal

        return patch(
            "src.modules.reminders.application.payment_block.resolve_amount_and_memo",
            AsyncMock(return_value=(Decimal(9_420_000), "INV-2026-0042")),
        )

    async def test_nhac_thanh_toan_thi_co_so_tai_khoan_va_ma_QR(self) -> None:
        reminder = make_reminder(channel="email", reminder_type="payment_overdue")
        send_email = AsyncMock()
        service, _ = make_service(
            reminder, send_email=send_email, owner=make_owner(**self._OWNER)
        )

        with self._fixed_amount():
            await service.deliver(reminder.id)

        kwargs = send_email.await_args.kwargs
        assert "1027123456" in kwargs["html"]
        # Phần chữ cũng phải có: nhiều trình đọc mail chặn ảnh theo mặc định.
        assert "1027123456" in kwargs["plain"]
        # Mã QR đi kèm dạng ảnh đính kèm (`cid:`) — Gmail cắt bỏ ảnh `data:base64`.
        assert kwargs["inline_images"] and "vietqr" in kwargs["inline_images"]
        assert 'src="cid:vietqr"' in kwargs["html"]
        # Số tiền và nội dung chuyển khoản in ra để khách đối chiếu.
        assert "9.420.000 ₫" in kwargs["html"]
        assert "INV-2026-0042" in kwargs["plain"]

    async def test_thu_hoi_tham_thi_KHONG_dinh_so_tai_khoan(self) -> None:
        # Gắn số tài khoản vào thư "hỏi thăm dự án" đọc lên như đi đòi nợ.
        reminder = make_reminder(channel="email", reminder_type="follow_up")
        send_email = AsyncMock()
        service, _ = make_service(
            reminder, send_email=send_email, owner=make_owner(**self._OWNER)
        )

        await service.deliver(reminder.id)

        kwargs = send_email.await_args.kwargs
        assert "1027123456" not in kwargs["html"]
        assert not kwargs.get("inline_images")

    async def test_chua_khai_thong_tin_nhan_tien_thi_thu_van_gui_binh_thuong(self) -> None:
        reminder = make_reminder(channel="email", reminder_type="payment_due")
        send_email = AsyncMock()
        service, _ = make_service(reminder, send_email=send_email, owner=make_owner())

        with self._fixed_amount():
            result = await service.deliver(reminder.id)

        assert result.status == "sent"
        assert not send_email.await_args.kwargs.get("inline_images")


class TestAnhFreelancerChenVaoThu:
    """Ảnh tự chèn (mã QR chụp sẵn, ảnh sản phẩm) phải nằm TRONG thân thư, không phải tệp đính kèm."""

    @staticmethod
    def _storage(data: bytes = b"\x89PNG\r\n\x1a\nfake"):  # type: ignore[no-untyped-def]
        # `download` trả (bytes, content_type) — trả sai hình dạng thì test xanh giả:
        # `load_image_bytes` nuốt mọi lỗi nên ảnh biến mất trong im lặng.
        return patch(
            "src.modules.reminders.application.delivery_service.object_storage",
            MagicMock(download=AsyncMock(return_value=(data, "image/png"))),
        )

    async def test_anh_di_kem_dang_cid_de_khach_mo_ra_la_thay(self) -> None:
        reminder = make_reminder(
            channel="email",
            attachments=[{"key": "reminders/u1/qr.png", "filename": "qr.png"}],
        )
        send_email = AsyncMock()
        service, _ = make_service(reminder, send_email=send_email)

        with self._storage():
            await service.deliver(reminder.id)

        kwargs = send_email.await_args.kwargs
        # `cid:` chứ không phải `data:base64` — Gmail cắt bỏ `data:`, khách sẽ thấy ô trống.
        assert 'src="cid:img0"' in kwargs["html"]
        assert kwargs["inline_images"]["img0"].startswith(b"\x89PNG")

    async def test_tai_anh_khong_ve_thi_van_gui_thu_chu_khong_nuot_luon(self) -> None:
        # Kho ảnh chập chờn không được phép nuốt cả lời nhắc: chữ mới là phần chính.
        reminder = make_reminder(
            channel="email", attachments=[{"key": "reminders/u1/qr.png"}]
        )
        send_email = AsyncMock()
        service, _ = make_service(reminder, send_email=send_email)

        with patch(
            "src.modules.reminders.application.delivery_service.object_storage",
            MagicMock(download=AsyncMock(side_effect=RuntimeError("kho ảnh sập"))),
        ):
            result = await service.deliver(reminder.id)

        assert result.status == "sent"
        assert "cid:img0" not in send_email.await_args.kwargs["html"]


class TestBaoChoFreelancerBietDaGui:
    """Hệ thống thay mặt người dùng liên hệ khách của họ — họ phải được biết."""

    async def test_beat_tu_gui_thi_bao_vao_chuong(self, notifications: MagicMock) -> None:
        reminder = make_reminder(channel="email")
        service, _ = make_service(reminder, send_email=AsyncMock())

        await service.deliver(reminder.id)  # unattended=True là mặc định của worker

        notifications.notify_reminder_sent.assert_awaited_once()
        kwargs = notifications.notify_reminder_sent.await_args.kwargs
        assert kwargs["client_name"] == "Quán cà phê Nắng"
        assert kwargs["recipient"] == "khach@example.com"

    async def test_bam_gui_ngay_thi_khong_bao_lai_lan_nua(self, notifications: MagicMock) -> None:
        """Người dùng vừa bấm nút và thấy kết quả hiện ra — chuông kêu nữa là nhiễu."""
        reminder = make_reminder(channel="email")
        service, _ = make_service(reminder, send_email=AsyncMock())

        await service.deliver(reminder.id, unattended=False)

        notifications.notify_reminder_sent.assert_not_awaited()

    async def test_kenh_both_luon_bao_du_bam_tay(self, notifications: MagicMock) -> None:
        """Chọn "both" là chủ động xin ghi lại trong app, phải tôn trọng lựa chọn đó."""
        reminder = make_reminder(channel="both")
        service, _ = make_service(reminder, send_email=AsyncMock())

        await service.deliver(reminder.id, unattended=False)

        notifications.notify_reminder_sent.assert_awaited_once()

    async def test_gui_hong_thi_khong_bao_da_gui(self, notifications: MagicMock) -> None:
        reminder = make_reminder(channel="email")
        service, _ = make_service(reminder, client=make_client(email=None))

        await service.deliver(reminder.id)

        notifications.notify_reminder_sent.assert_not_awaited()
        notifications.notify_reminder_failed.assert_awaited_once()


class TestKenhInApp:
    async def test_in_app_chi_bao_freelancer_khong_dung_toi_khach(self) -> None:
        send_email = AsyncMock()
        reminder = make_reminder(channel="in_app")
        service, _ = make_service(reminder, send_email=send_email)

        result = await service.deliver(reminder.id)

        send_email.assert_not_awaited()
        assert reminder.status == "sent"
        assert result.delivered is True

    async def test_in_app_van_bao_ke_ca_khi_bam_tay(self, notifications: MagicMock) -> None:
        """Ở kênh này thông báo CHÍNH LÀ việc gửi — bỏ qua là lời nhắc không làm gì hết."""
        reminder = make_reminder(channel="in_app")
        service, _ = make_service(reminder)

        await service.deliver(reminder.id, unattended=False)

        notifications.notify_reminder_due.assert_awaited_once()

    async def test_both_gui_ca_email_lan_thong_bao(self) -> None:
        send_email = AsyncMock()
        reminder = make_reminder(channel="both")
        service, _ = make_service(reminder, send_email=send_email)

        result = await service.deliver(reminder.id)

        send_email.assert_awaited_once()
        assert reminder.status == "sent"
        assert "ghi lại thông báo cho bạn" in result.detail


def make_zalo_service(reminder, *, oa_token, zalo_user_id, zalo_client=None):  # type: ignore[no-untyped-def]
    """Như make_service nhưng gắn token OA cho owner + zalo_user_id cho client, và tiêm
    zalo_client giả để khẳng định 'đã gọi gửi tới đúng người'."""
    client = make_client()
    client.id = uuid.uuid4()
    client.zalo_user_id = zalo_user_id
    repo = AsyncMock()
    repo.get_for_delivery.return_value = reminder
    repo.resolve_target.return_value = (client, "Thiết kế logo")
    owner = MagicMock()
    owner.full_name = "Huỳnh Hoa"
    owner.email = "huynhhoa@example.com"
    owner.zalo_oa_access_token = oa_token
    repo.get_owner.return_value = owner
    service = ReminderDeliveryService(
        db=make_db(),
        send_email=AsyncMock(),
        repo=repo,
        zalo_client=zalo_client or AsyncMock(),
    )
    return service, repo, client


class TestKenhZalo:
    async def test_gui_cs_thanh_cong_khi_da_ket_noi(self, notifications: MagicMock) -> None:
        """Có token OA + khách đã follow (có zalo_user_id) → gửi CS thật, đánh dấu sent."""
        reminder = make_reminder(channel="zalo")
        zalo = AsyncMock()
        service, repo, _ = make_zalo_service(
            reminder, oa_token="oa-token", zalo_user_id="follower-123", zalo_client=zalo
        )

        result = await service.deliver(reminder.id)

        zalo.send_cs_message.assert_awaited_once()
        assert zalo.send_cs_message.await_args.kwargs["user_id"] == "follower-123"
        assert reminder.status == "sent"
        assert result.delivered is True
        record = repo.add_delivery_record.await_args.kwargs
        assert record["channel"] == "zalo" and record["outcome"] == "success"

    async def test_chua_ket_noi_oa_thi_that_bai_khong_gia_gui(
        self, notifications: MagicMock
    ) -> None:
        """Freelancer chưa nối OA → báo thẳng thất bại, KHÔNG giả 'đã gửi'."""
        reminder = make_reminder(channel="zalo")
        zalo = AsyncMock()
        service, _, _ = make_zalo_service(
            reminder, oa_token=None, zalo_user_id="follower-123", zalo_client=zalo
        )

        result = await service.deliver(reminder.id)

        zalo.send_cs_message.assert_not_awaited()
        assert reminder.status == "failed"
        assert "chưa kết nối Zalo OA" in result.detail

    async def test_khach_chua_follow_o_che_do_real_thi_that_bai(
        self, notifications: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Chế độ real + khách chưa follow OA (thiếu zalo_user_id) → thất bại, không gửi bừa."""
        monkeypatch.setattr(_delivery_mod.settings, "zalo_mode", "real")
        reminder = make_reminder(channel="zalo")
        zalo = AsyncMock()
        service, _, _ = make_zalo_service(
            reminder, oa_token="oa-token", zalo_user_id=None, zalo_client=zalo
        )

        result = await service.deliver(reminder.id)

        zalo.send_cs_message.assert_not_awaited()
        assert reminder.status == "failed"
        assert "chưa kết nối Zalo" in result.detail


class TestRetry:
    async def test_loi_tam_thoi_thi_giu_pending_va_xin_thu_lai(self) -> None:
        send_email = AsyncMock(side_effect=smtplib.SMTPServerDisconnected("mail server chết"))
        reminder = make_reminder(channel="email", retry_count=0)
        service, repo = make_service(reminder, send_email=send_email)

        result = await service.deliver(reminder.id)

        assert result.should_retry is True
        assert result.status == "pending"
        assert reminder.retry_count == 1
        assert reminder.status == "pending"  # vẫn chờ để lượt sau còn gửi được
        assert repo.add_delivery_record.await_args.kwargs["outcome"] == "failure"

    async def test_het_luot_thu_thi_bao_that_bai_cho_nguoi_dung(self) -> None:
        send_email = AsyncMock(side_effect=smtplib.SMTPServerDisconnected("vẫn chết"))
        reminder = make_reminder(channel="email", retry_count=MAX_DELIVERY_ATTEMPTS - 1)
        service, _ = make_service(reminder, send_email=send_email)

        result = await service.deliver(reminder.id)

        assert reminder.retry_count == MAX_DELIVERY_ATTEMPTS
        assert reminder.status == "failed"
        assert result.should_retry is False
        assert str(MAX_DELIVERY_ATTEMPTS) in result.detail

    async def test_retry_count_khong_bao_gio_vuot_qua_rang_buoc_db(self) -> None:
        """Cột có CHECK `retry_count BETWEEN 0 AND 3` — vượt là vỡ ở tầng database."""
        send_email = AsyncMock(side_effect=TimeoutError("chậm"))
        reminder = make_reminder(channel="email", retry_count=MAX_DELIVERY_ATTEMPTS - 1)
        service, _ = make_service(reminder, send_email=send_email)

        await service.deliver(reminder.id)

        assert reminder.retry_count <= 3

    async def test_dia_chi_sai_thi_bo_cuoc_ngay_du_la_loi_smtp(self) -> None:
        send_email = AsyncMock(side_effect=smtplib.SMTPRecipientsRefused({}))
        reminder = make_reminder(channel="email")
        service, _ = make_service(reminder, send_email=send_email)

        result = await service.deliver(reminder.id)

        assert result.should_retry is False
        assert reminder.status == "failed"
        assert reminder.retry_count == 0
