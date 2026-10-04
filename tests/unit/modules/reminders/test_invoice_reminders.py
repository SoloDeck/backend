"""Lời nhắc thanh toán tự đặt khi gửi hóa đơn — theo quy tắc "Nhắc trước khi hóa đơn tới hạn".

Lời nhắc có thể đi THẲNG tới khách hàng thật, nên những thứ được khoá ở đây là: mọi thông số lấy từ
CHÍNH quy tắc của người dùng (số ngày, giờ, kênh, tự gửi/chờ duyệt, nội dung mẫu, công tắc bật/tắt),
ngày nhắc luôn sau ngày gửi, không đặt cho khách chưa có email khi gửi bằng email, lỗi DB không phá
việc gửi hóa đơn, và hóa đơn đã thu đủ thì không nhắc.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.exc import SQLAlchemyError

from src.modules.reminders.application import invoice_reminders as mod
from src.modules.reminders.application.invoice_reminders import (
    REASON_DISABLED,
    REASON_ERROR,
    REASON_NO_CLIENT_EMAIL,
    REASON_TOO_SOON,
    PaymentReminderOutcome,
    invoice_is_settled,
    project_label_for,
    refresh_invoice_reminder_amounts,
    remaining_amount_text,
    reminder_time_before_due,
    retire_invoice_payment_reminders,
    schedule_invoice_payment_reminder,
)

ICT = ZoneInfo("Asia/Ho_Chi_Minh")
# 16:30 UTC = 23:30 giờ Việt Nam ngày 03/10.
NOW = datetime(2026, 10, 3, 16, 30, tzinfo=UTC)


@dataclass
class InvoiceStub:
    id: uuid.UUID
    owner_user_id: uuid.UUID
    invoice_number: str = "INV-20261003-3AF1"
    due_date: date = date(2026, 10, 17)
    total: int = 83_000_000
    amount_paid: int = 0
    currency: str = "VND"


@dataclass
class ClientStub:
    name: str = "Nguyễn Văn Mười"
    email: str | None = "ngvan10@example.com"


@dataclass
class OwnerStub:
    timezone: str | None = "Asia/Ho_Chi_Minh"


def an_invoice(**over) -> InvoiceStub:  # type: ignore[no-untyped-def]
    return InvoiceStub(id=uuid.uuid4(), owner_user_id=uuid.uuid4(), **over)


def a_rule(**over):  # type: ignore[no-untyped-def]
    """Quy tắc "tới hạn" mặc định: trước hạn 3 ngày, 9h, email, chờ duyệt, mẫu mặc định."""
    values = {
        "rule_type": "payment_due",
        "is_enabled": True,
        "offset_days": 3,
        "channel": "email",
        "auto_send": False,
        "send_at_hour": 9,
        "message_template": None,
    }
    values.update(over)
    return SimpleNamespace(**values)


def a_db() -> AsyncMock:
    """Session giả. `begin_nested()` là hàm ĐỒNG BỘ trả về async context manager."""
    db = AsyncMock()
    db.begin_nested = MagicMock(return_value=AsyncMock())
    return db


async def schedule(rule=None, *, invoice=None, client="mac-dinh", now=NOW, rules=None):  # type: ignore[no-untyped-def]
    """Chạy hàm thật với quy tắc/khách giả. Trả `(kết quả, kwargs truyền vào create, db)`."""
    db = a_db()
    invoice = invoice or an_invoice()
    client = ClientStub() if client == "mac-dinh" else client
    with (
        patch.object(mod, "ReminderRulesService") as service_cls,
        patch.object(mod, "RemindersRepository") as repo_cls,
    ):
        service_cls.return_value.list_for_user = AsyncMock(
            return_value=rules if rules is not None else [rule or a_rule()]
        )
        repo_cls.return_value.create = AsyncMock(side_effect=lambda **v: SimpleNamespace(**v))
        outcome = await schedule_invoice_payment_reminder(
            db, invoice=invoice, client=client, owner=OwnerStub(), now=now
        )
        created = (
            repo_cls.return_value.create.await_args.kwargs
            if repo_cls.return_value.create.await_args
            else None
        )
    return outcome, created, db


class TestGioNhac:
    def test_ngay_cach_han_n_ngay_theo_gio_nguoi_dung_roi_doi_ve_utc(self) -> None:
        # Hạn 17/10, trước 3 ngày = 14/10; 9h sáng ICT = 02:00 UTC cùng ngày.
        assert reminder_time_before_due(date(2026, 10, 17), 3, "Asia/Ho_Chi_Minh") == datetime(
            2026, 10, 14, 2, 0, tzinfo=UTC
        )

    def test_gio_gui_theo_quy_tac(self) -> None:
        assert reminder_time_before_due(
            date(2026, 10, 17), 3, "Asia/Ho_Chi_Minh", hour=14
        ) == datetime(2026, 10, 14, 7, 0, tzinfo=UTC)

    def test_theo_lich_cua_nguoi_dung_o_mui_gio_khac(self) -> None:
        # 9h sáng ở New York (UTC-4 mùa hè) = 13:00 UTC.
        assert reminder_time_before_due(date(2026, 10, 17), 2, "America/New_York") == datetime(
            2026, 10, 15, 13, 0, tzinfo=UTC
        )

    def test_qua_ranh_thang(self) -> None:
        assert reminder_time_before_due(date(2026, 11, 1), 2, "Asia/Ho_Chi_Minh") == datetime(
            2026, 10, 30, 2, 0, tzinfo=UTC
        )

    @pytest.mark.parametrize("tz", [None, "", "Khong/Ton_Tai"])
    def test_mui_gio_rac_thi_dung_gio_viet_nam_chu_khong_no(self, tz) -> None:  # type: ignore[no-untyped-def]
        assert reminder_time_before_due(date(2026, 10, 17), 3, tz) == datetime(
            2026, 10, 14, 2, 0, tzinfo=UTC
        )


class TestDatTheoQuyTac:
    async def test_quy_tac_mac_dinh_thi_cho_duyet_va_dung_loai_kenh_gio(self) -> None:
        invoice = an_invoice()
        outcome, created, db = await schedule(invoice=invoice)

        assert outcome.reason is None and outcome.reminder is not None
        assert created["reminder_type"] == "payment_due"
        assert created["target_type"] == "invoice"
        assert created["target_id"] == invoice.id
        assert created["owner_user_id"] == invoice.owner_user_id
        assert created["channel"] == "email"
        assert created["status"] == "pending"
        assert created["scheduled_at"] == datetime(2026, 10, 14, 2, 0, tzinfo=UTC)  # 9h ICT
        # Công tắc "Tự động gửi" tắt (mặc định) nên nằm chờ duyệt, và có nhãn "Tự động" ở tab.
        assert created["requires_approval"] is True
        assert created["created_by_rule"] is True
        assert outcome.requires_approval is True
        assert outcome.days_before_due == 3
        db.begin_nested.assert_called_once()  # ghi trong SAVEPOINT

    async def test_cot_tu_gui_cu_con_bat_van_phai_cho_duyet(self) -> None:
        """Công tắc "tự gửi" đã bỏ: người dùng cũ còn cột True cũng không có đường tự gửi."""
        outcome, created, _ = await schedule(a_rule(auto_send=True))

        assert created["requires_approval"] is True
        assert outcome.requires_approval is True

    async def test_so_ngay_gio_va_kenh_deu_lay_tu_quy_tac(self) -> None:
        outcome, created, _ = await schedule(a_rule(offset_days=5, send_at_hour=14, channel="both"))

        assert created["scheduled_at"] == datetime(2026, 10, 12, 7, 0, tzinfo=UTC)  # 14h ICT, 12/10
        assert created["channel"] == "both"
        assert outcome.days_before_due == 5

    async def test_noi_dung_la_mau_mac_dinh_dien_thong_tin_that(self) -> None:
        _, created, _ = await schedule()

        message = created["message_preview"]
        assert "Nguyễn Văn Mười" in message
        assert "INV-20261003-3AF1" in message
        assert "17/10/2026" in message
        assert "83.000.000 ₫" in message  # số còn lại
        assert "{" not in message, "còn chỗ giữ chỗ chưa điền"

    async def test_noi_dung_tu_soan_cua_freelancer_duoc_dung(self) -> None:
        rule = a_rule(message_template="Gửi {client_name}: {invoice_number} hạn {due_date}.")
        _, created, _ = await schedule(rule)

        assert (
            created["message_preview"] == "Gửi Nguyễn Văn Mười: INV-20261003-3AF1 hạn 17/10/2026."
        )

    async def test_da_thu_mot_phan_thi_ghi_so_con_lai(self) -> None:
        _, created, _ = await schedule(invoice=an_invoice(amount_paid=30_000_000))

        assert "53.000.000 ₫" in created["message_preview"]


class TestKhongDat:
    async def test_quy_tac_dang_tat_thi_gui_hoa_don_cung_khong_dat_loi_nhac(self) -> None:
        outcome, created, _ = await schedule(a_rule(is_enabled=False))

        assert outcome.reminder is None and outcome.reason == REASON_DISABLED
        assert created is None

    async def test_khong_tim_thay_quy_tac_thi_coi_nhu_tat(self) -> None:
        outcome, created, _ = await schedule(rules=[a_rule(rule_type="proposal_follow_up")])

        assert outcome.reason == REASON_DISABLED and created is None

    @pytest.mark.parametrize("channel", ["email", "both"])
    @pytest.mark.parametrize("client", [None, ClientStub(email=None), ClientStub(email="   ")])
    async def test_gui_cho_khach_bang_email_ma_khach_chua_co_email_thi_khong_dat(
        self,
        channel,
        client,  # type: ignore[no-untyped-def]
    ) -> None:
        outcome, created, _ = await schedule(a_rule(channel=channel), client=client)

        assert outcome.reason == REASON_NO_CLIENT_EMAIL and created is None
        assert outcome.days_before_due == 3  # vẫn nêu để giải thích

    @pytest.mark.parametrize("channel", ["in_app", "zalo"])
    async def test_kenh_khong_dung_email_thi_khach_khong_co_email_van_dat_duoc(
        self,
        channel,  # type: ignore[no-untyped-def]
    ) -> None:
        outcome, created, _ = await schedule(a_rule(channel=channel), client=ClientStub(email=None))

        assert outcome.reminder is not None
        assert created["channel"] == channel

    async def test_loi_db_khong_lam_hong_viec_gui_hoa_don(self) -> None:
        """Thư hóa đơn đã rời máy chủ trước khi hàm này chạy; ném lỗi ra là kéo hóa đơn về nháp."""
        db = a_db()
        with (
            patch.object(mod, "ReminderRulesService") as service_cls,
            patch.object(mod, "RemindersRepository") as repo_cls,
        ):
            service_cls.return_value.list_for_user = AsyncMock(return_value=[a_rule()])
            repo_cls.return_value.create = AsyncMock(side_effect=SQLAlchemyError("boom"))
            outcome = await schedule_invoice_payment_reminder(
                db, invoice=an_invoice(), client=ClientStub(), owner=OwnerStub(), now=NOW
            )

        assert outcome.reminder is None and outcome.reason == REASON_ERROR

    async def test_loi_khi_doc_quy_tac_cung_duoc_nuot(self) -> None:
        db = a_db()
        with patch.object(mod, "ReminderRulesService") as service_cls:
            service_cls.return_value.list_for_user = AsyncMock(side_effect=SQLAlchemyError("boom"))
            outcome = await schedule_invoice_payment_reminder(
                db, invoice=an_invoice(), client=ClientStub(), owner=OwnerStub(), now=NOW
            )

        assert outcome.reason == REASON_ERROR


class TestHanQuaGan:
    """Ngày nhắc (hạn − N ngày) phải SAU ngày gửi, tính theo NGÀY chứ không theo giờ."""

    @pytest.mark.parametrize(
        "due",
        [date(2026, 10, 3), date(2026, 10, 5), date(2026, 10, 6)],
        ids=["han-hom-nay", "han-con-2-ngay", "han-con-dung-3-ngay"],
    )
    async def test_han_den_het_n_ngay_thi_khong_dat(self, due) -> None:  # type: ignore[no-untyped-def]
        """Quy tắc 3 ngày: hạn 06/10 thì ngày nhắc là 03/10 — chính hôm nay, không sau ngày gửi."""
        outcome, created, _ = await schedule(invoice=an_invoice(due_date=due))

        assert outcome.reason == REASON_TOO_SOON and created is None
        assert outcome.days_before_due == 3

    async def test_han_cach_n_cong_1_ngay_thi_dat(self) -> None:
        outcome, created, _ = await schedule(invoice=an_invoice(due_date=date(2026, 10, 7)))

        assert outcome.reminder is not None
        assert created["scheduled_at"] == datetime(2026, 10, 4, 2, 0, tzinfo=UTC)

    @pytest.mark.parametrize("gio", [0, 8, 9, 10, 23])
    async def test_ket_qua_khong_doi_theo_gio_gui_trong_ngay(self, gio) -> None:  # type: ignore[no-untyped-def]
        """Trước đây so theo giờ nên "còn đúng N ngày" đổi kết quả theo gửi lúc 8h hay 10h sáng."""
        now = datetime(2026, 10, 3, gio, 5, tzinfo=ICT).astimezone(UTC)
        too_soon, _, _ = await schedule(invoice=an_invoice(due_date=date(2026, 10, 6)), now=now)
        enough, _, _ = await schedule(invoice=an_invoice(due_date=date(2026, 10, 7)), now=now)

        assert too_soon.reason == REASON_TOO_SOON
        assert enough.reminder is not None

    async def test_quy_tac_0_ngay_thi_nhac_dung_ngay_den_han(self) -> None:
        outcome, created, _ = await schedule(a_rule(offset_days=0))

        assert outcome.reminder is not None
        assert created["scheduled_at"] == datetime(2026, 10, 17, 2, 0, tzinfo=UTC)

    async def test_quy_tac_0_ngay_ma_han_la_hom_nay_thi_khong_dat(self) -> None:
        outcome, _, _ = await schedule(
            a_rule(offset_days=0), invoice=an_invoice(due_date=date(2026, 10, 3))
        )

        assert outcome.reason == REASON_TOO_SOON


class TestKetQuaTraVeChoWeb:
    def test_da_dat_thi_co_gio_nhac_va_khong_co_ly_do(self) -> None:
        when = datetime(2026, 10, 14, 2, 0, tzinfo=UTC)
        outcome = PaymentReminderOutcome(
            reminder=SimpleNamespace(scheduled_at=when), days_before_due=3, requires_approval=True
        )

        assert outcome.as_response() == {
            "scheduled": True,
            "scheduled_at": when,
            "days_before_due": 3,
            "requires_approval": True,
            "reason": None,
        }

    def test_khong_dat_thi_co_ly_do(self) -> None:
        outcome = PaymentReminderOutcome(reason=REASON_TOO_SOON, days_before_due=3)

        assert outcome.as_response() == {
            "scheduled": False,
            "scheduled_at": None,
            "days_before_due": 3,
            "requires_approval": False,
            "reason": "too_soon",
        }


class TestSoTienConLai:
    def test_ghi_dang_nghin_cham_va_dau_dong(self) -> None:
        assert remaining_amount_text(an_invoice(total=83_000_000, amount_paid=0)) == "83.000.000 ₫"
        assert remaining_amount_text(an_invoice(total=83_000_000, amount_paid=30_000_000)) == (
            "53.000.000 ₫"
        )


class TestCapNhatSoTienKhiThuMotPhan:
    @staticmethod
    def db_with(*messages: str | None):  # type: ignore[no-untyped-def]
        reminders = [SimpleNamespace(message_preview=m) for m in messages]
        db = AsyncMock()
        db.execute.return_value = MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=reminders)))
        )
        return db, reminders

    async def test_doi_dung_chuoi_so_tien_cu_thanh_so_moi(self) -> None:
        db, (reminder,) = self.db_with("Còn 83.000.000 ₫, hạn 17/10. Xin chuyển 83.000.000 ₫.")

        changed = await refresh_invoice_reminder_amounts(
            db,
            owner_user_id=uuid.uuid4(),
            invoice_id=uuid.uuid4(),
            old_text="83.000.000 ₫",
            new_text="53.000.000 ₫",
        )

        assert changed == 1
        assert reminder.message_preview == "Còn 53.000.000 ₫, hạn 17/10. Xin chuyển 53.000.000 ₫."

    async def test_chu_freelancer_da_sua_khong_con_so_cu_thi_khong_dung_toi(self) -> None:
        db, (reminder,) = self.db_with("Anh chị chuyển giúp em sớm nhé.")

        changed = await refresh_invoice_reminder_amounts(
            db,
            owner_user_id=uuid.uuid4(),
            invoice_id=uuid.uuid4(),
            old_text="83.000.000 ₫",
            new_text="53.000.000 ₫",
        )

        assert changed == 0
        assert reminder.message_preview == "Anh chị chuyển giúp em sớm nhé."

    async def test_noi_dung_rong_khong_no(self) -> None:
        db, _ = self.db_with(None)

        assert (
            await refresh_invoice_reminder_amounts(
                db, owner_user_id=uuid.uuid4(), invoice_id=uuid.uuid4(), old_text="a", new_text="b"
            )
            == 0
        )

    @pytest.mark.parametrize(("old", "new"), [("", "x"), ("a", "a")])
    async def test_khong_co_gi_doi_thi_khong_cham_toi_db(self, old, new) -> None:  # type: ignore[no-untyped-def]
        db, _ = self.db_with("a")

        assert (
            await refresh_invoice_reminder_amounts(
                db, owner_user_id=uuid.uuid4(), invoice_id=uuid.uuid4(), old_text=old, new_text=new
            )
            == 0
        )
        db.execute.assert_not_awaited()


class TestHuyKhiDaThu:
    async def test_tra_so_loi_nhac_da_huy(self) -> None:
        db = AsyncMock()
        db.execute.return_value = MagicMock(rowcount=2)
        count = await retire_invoice_payment_reminders(
            db, owner_user_id=uuid.uuid4(), invoice_id=uuid.uuid4()
        )
        assert count == 2

    async def test_cau_lenh_chi_nham_loi_nhac_thanh_toan_dang_cho_cua_dung_hoa_don(self) -> None:
        db = AsyncMock()
        db.execute.return_value = MagicMock(rowcount=0)
        owner_id, invoice_id = uuid.uuid4(), uuid.uuid4()
        await retire_invoice_payment_reminders(db, owner_user_id=owner_id, invoice_id=invoice_id)

        statement = db.execute.await_args.args[0]
        sql = str(statement.compile(compile_kwargs={"literal_binds": False}))
        params = statement.compile().params
        assert sql.startswith("UPDATE reminders")
        for column in ("owner_user_id", "target_type", "target_id", "status", "reminder_type"):
            assert f"reminders.{column}" in sql, f"thiếu điều kiện {column}"
        assert "invoice" in params.values()
        assert "pending" in params.values()
        assert "cancelled" in params.values()
        assert owner_id in params.values() and invoice_id in params.values()
        # Chỉ hai loại thanh toán; lời nhắc hỏi thăm tự soạn của freelancer thì không đụng.
        assert any(
            isinstance(v, list | tuple | set | frozenset)
            and set(v) == {"payment_due", "payment_overdue"}
            for v in params.values()
        )


def a_reminder(**over):  # type: ignore[no-untyped-def]
    reminder = MagicMock()
    reminder.target_type = over.get("target_type", "invoice")
    reminder.reminder_type = over.get("reminder_type", "payment_due")
    reminder.target_id = uuid.uuid4()
    reminder.owner_user_id = uuid.uuid4()
    return reminder


class TestHoaDonDaXong:
    @pytest.mark.parametrize("status", ["paid", "void"])
    async def test_da_thu_du_hoac_da_huy_thi_khong_con_gi_de_nhac(self, status) -> None:  # type: ignore[no-untyped-def]
        db = AsyncMock()
        db.scalar.return_value = status
        assert await invoice_is_settled(db, a_reminder()) is True

    @pytest.mark.parametrize("status", ["sent", "partially_paid", "overdue", "draft", None])
    async def test_con_no_thi_van_nhac(self, status) -> None:  # type: ignore[no-untyped-def]
        db = AsyncMock()
        db.scalar.return_value = status
        assert await invoice_is_settled(db, a_reminder()) is False

    async def test_ca_hai_loai_thanh_toan_deu_duoc_kiem(self) -> None:
        for reminder_type in ("payment_due", "payment_overdue"):
            db = AsyncMock()
            db.scalar.return_value = "paid"
            assert await invoice_is_settled(db, a_reminder(reminder_type=reminder_type)) is True

    @pytest.mark.parametrize(
        "over",
        [
            {"reminder_type": "follow_up"},
            {"reminder_type": "custom"},
            {"target_type": "deal"},
            {"target_type": "contract"},
        ],
    )
    async def test_loi_nhac_khong_phai_thanh_toan_hoa_don_thi_khong_dong_toi_db(self, over) -> None:  # type: ignore[no-untyped-def]
        db = AsyncMock()
        db.scalar.return_value = "paid"
        assert await invoice_is_settled(db, a_reminder(**over)) is False
        db.scalar.assert_not_awaited()


class TestNhanChanThu:
    async def test_hoa_don_thi_lay_ten_du_an_chu_khong_phai_ma_hoa_don(self) -> None:
        db = AsyncMock()
        db.scalar.return_value = "English center"
        label = await project_label_for(db, a_reminder(), "INV-20261003-3AF1")
        assert label == "English center"

    @pytest.mark.parametrize("found", [None, "", "   ", MagicMock()])
    async def test_khong_tra_duoc_ten_du_an_thi_giu_nhan_cu(self, found) -> None:  # type: ignore[no-untyped-def]
        db = AsyncMock()
        db.scalar.return_value = found
        assert await project_label_for(db, a_reminder(), "INV-1") == "INV-1"

    async def test_doi_tuong_khac_hoa_don_thi_giu_nguyen_nhan(self) -> None:
        db = AsyncMock()
        assert await project_label_for(db, a_reminder(target_type="deal"), "English center") == (
            "English center"
        )
        db.scalar.assert_not_awaited()
