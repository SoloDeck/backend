"""Bộ máy quy tắc nhắc tự động.

Nó chạy MỖI NGÀY trên toàn bộ user, và thứ nó sinh ra sẽ được gửi tới khách hàng thật.
Hai thứ được phủ kỹ nhất ở đây là hai thứ hỏng thì hỏng nặng: sinh trùng (khách nhận ba
mươi email giống nhau trong một tháng) và lời nhắc chờ duyệt lọt ra ngoài.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

from src.modules.reminders.application.auto_scheduler import AutoReminderScheduler, Candidate
from src.modules.reminders.domain.value_objects.reminder_rules import (
    REPEATABLE_RULES,
    RULE_DEFAULTS,
    RuleType,
)


def make_rule(rule_type: str = "payment_overdue", **overrides) -> MagicMock:  # type: ignore[no-untyped-def]
    rule = MagicMock()
    rule.rule_type = rule_type
    rule.owner_user_id = overrides.get("owner_user_id", uuid.uuid4())
    rule.is_enabled = overrides.get("is_enabled", True)
    rule.offset_days = overrides.get("offset_days", 1)
    rule.repeat_every_days = overrides.get("repeat_every_days", 7)
    rule.channel = overrides.get("channel", "email")
    rule.auto_send = overrides.get("auto_send", False)
    rule.send_at_hour = overrides.get("send_at_hour", 9)
    rule.message_template = overrides.get("message_template", None)
    return rule


def make_candidate(rule: MagicMock, **overrides) -> Candidate:  # type: ignore[no-untyped-def]
    return Candidate(
        owner_user_id=overrides.get("owner_user_id", rule.owner_user_id),
        target_type=overrides.get("target_type", "invoice"),
        target_id=overrides.get("target_id", uuid.uuid4()),
        rule=rule,
        message=overrides.get("message", "Chào anh/chị, em nhắc hoá đơn ạ."),
        client_name=overrides.get("client_name", "Quán cà phê Nắng"),
    )


class TestDanhMucQuyTac:
    def test_dung_nam_quy_tac_va_deu_co_mac_dinh(self) -> None:
        assert len(RuleType) == 5
        assert set(RULE_DEFAULTS) == set(RuleType)

    def test_tai_ket_noi_mac_dinh_TAT(self) -> None:
        """Quy tắc duy nhất chạm tới khách không có việc gì đang làm dở. Bật nhầm là email
        hàng loạt tới toàn bộ khách cũ."""
        assert RULE_DEFAULTS[RuleType.RE_ENGAGEMENT].is_enabled is False

    def test_bon_quy_tac_con_lai_bat_san(self) -> None:
        for rule_type in RuleType:
            if rule_type is RuleType.RE_ENGAGEMENT:
                continue
            assert RULE_DEFAULTS[rule_type].is_enabled is True, rule_type

    def test_chi_qua_han_va_tai_ket_noi_moi_lap_lai(self) -> None:
        """Nhắc mãi một báo giá khách đã lờ đi thì không phải chăm sóc mà là làm phiền."""
        assert REPEATABLE_RULES == {RuleType.PAYMENT_OVERDUE, RuleType.RE_ENGAGEMENT}
        for rule_type in RuleType:
            spec = RULE_DEFAULTS[rule_type]
            if rule_type in REPEATABLE_RULES:
                assert spec.repeat_every_days is not None, rule_type
            else:
                assert spec.repeat_every_days is None, rule_type

    def test_thu_tu_theo_vong_doi_deal(self) -> None:
        """Màn cài đặt hiện theo thứ tự này — đọc xuôi theo việc thật đang diễn ra."""
        assert [r.value for r in RuleType] == [
            "proposal_follow_up",
            "contract_signing_nudge",
            "payment_due",
            "payment_overdue",
            "re_engagement",
        ]


class TestDungLoiNhac:
    def test_chua_bat_tu_gui_thi_phai_cho_duyet(self) -> None:
        """Cột `requires_approval` là thứ DUY NHẤT chặn beat gửi thẳng cho khách."""
        scheduler = AutoReminderScheduler(db=MagicMock())
        reminder = scheduler._build_reminder(make_candidate(make_rule(auto_send=False)))

        assert reminder.requires_approval is True
        assert reminder.created_by_rule is True
        assert reminder.status == "pending"

    def test_bat_tu_gui_thi_di_thang(self) -> None:
        scheduler = AutoReminderScheduler(db=MagicMock())
        reminder = scheduler._build_reminder(make_candidate(make_rule(auto_send=True)))

        assert reminder.requires_approval is False

    def test_noi_dung_va_kenh_lay_tu_quy_tac(self) -> None:
        scheduler = AutoReminderScheduler(db=MagicMock())
        candidate = make_candidate(make_rule(channel="both"), message="Nội dung nhắc")
        reminder = scheduler._build_reminder(candidate)

        assert reminder.channel == "both"
        assert reminder.message_preview == "Nội dung nhắc"


class TestGioGui:
    def test_hen_dung_gio_nguoi_dung_chon_chu_khong_phai_luc_quet(self) -> None:
        """Lượt quét chạy 1 giờ sáng — không ai muốn nhận email công việc lúc đó."""
        scheduler = AutoReminderScheduler(db=MagicMock())
        rule = make_rule(send_at_hour=9)
        scheduler._timezones = {rule.owner_user_id: "Asia/Ho_Chi_Minh"}

        scheduled = scheduler._scheduled_at(rule)

        assert scheduled.astimezone(ZoneInfo("Asia/Ho_Chi_Minh")).hour == 9

    def test_qua_gio_hom_nay_thi_day_sang_mai(self) -> None:
        scheduler = AutoReminderScheduler(db=MagicMock())
        rule = make_rule(send_at_hour=0)  # 0h chắc chắn đã trôi qua
        scheduler._timezones = {rule.owner_user_id: "Asia/Ho_Chi_Minh"}

        assert scheduler._scheduled_at(rule) > datetime.now(UTC)

    def test_mui_gio_rac_khong_lam_hong_ca_luot_quet(self) -> None:
        """Một dòng dữ liệu hỏng không được phép chặn lời nhắc của mọi user khác."""
        scheduler = AutoReminderScheduler(db=MagicMock())
        rule = make_rule()
        scheduler._timezones = {rule.owner_user_id: "Khong/TonTai"}

        assert scheduler._scheduled_at(rule) is not None


def scheduler_with_existing(*rows: tuple) -> AutoReminderScheduler:  # type: ignore[type-arg]
    """Scheduler với database giả đã sẵn có mấy lời nhắc `rows`."""
    db = AsyncMock()
    result = MagicMock()
    result.all.return_value = list(rows)
    db.execute.return_value = result
    return AutoReminderScheduler(db=db)


class TestChongTrung:
    """Không lọc thì một hoá đơn quá hạn sinh một lời nhắc MỖI NGÀY — tháng sau khách nhận
    ba mươi email giống hệt nhau và freelancer mất khách."""

    async def test_chua_co_gi_thi_giu_lai_het(self) -> None:
        scheduler = scheduler_with_existing()
        candidates = [make_candidate(make_rule()) for _ in range(3)]

        assert len(await scheduler._drop_duplicates(candidates)) == 3

    async def test_da_co_loi_nhac_cho_dung_doi_tuong_thi_bo(self) -> None:
        rule = make_rule()
        candidate = make_candidate(rule)
        scheduler = scheduler_with_existing(
            (candidate.owner_user_id, "invoice", candidate.target_id, rule.rule_type)
        )

        assert await scheduler._drop_duplicates([candidate]) == []

    async def test_khac_loai_nhac_thi_van_tao(self) -> None:
        """Cùng một hoá đơn có thể vừa đáng nhắc sắp-tới-hạn vừa đáng nhắc quá-hạn ở hai
        thời điểm khác nhau — không được coi là trùng."""
        rule = make_rule(rule_type="payment_due")
        candidate = make_candidate(rule)
        scheduler = scheduler_with_existing(
            (candidate.owner_user_id, "invoice", candidate.target_id, "payment_overdue")
        )

        assert len(await scheduler._drop_duplicates([candidate])) == 1

    async def test_khac_chu_so_huu_thi_khong_anh_huong_nhau(self) -> None:
        """Hai freelancer khác nhau, không ai được chặn lời nhắc của người kia."""
        rule = make_rule()
        candidate = make_candidate(rule)
        scheduler = scheduler_with_existing(
            (uuid.uuid4(), "invoice", candidate.target_id, rule.rule_type)
        )

        assert len(await scheduler._drop_duplicates([candidate])) == 1

    async def test_trung_NGAY_TRONG_mot_luot_quet(self) -> None:
        """Hai hoá đơn cùng một khách sinh ra hai ứng viên `re_engagement` giống hệt nhau
        mà chưa cái nào kịp vào database — lọc theo DB không bắt được ca này."""
        rule = make_rule(rule_type="re_engagement")
        client_id = uuid.uuid4()
        a = make_candidate(rule, target_type="client", target_id=client_id)
        b = make_candidate(rule, target_type="client", target_id=client_id)
        scheduler = scheduler_with_existing()

        assert len(await scheduler._drop_duplicates([a, b])) == 1

    async def test_khong_co_ung_vien_thi_khong_hoi_database(self) -> None:
        """Phần lớn ngày sẽ không có gì để nhắc — đừng bắn truy vấn vô ích."""
        scheduler = scheduler_with_existing()

        assert await scheduler._drop_duplicates([]) == []
        scheduler.db.execute.assert_not_awaited()


class TestDinhDangTin:
    def test_tinh_so_tien_CON_LAI_chu_khong_phai_tong(self) -> None:
        """Khách trả một phần rồi mà nhắc nguyên tổng thì thành đòi thừa tiền."""
        invoice = MagicMock(total=10_000_000, amount_paid=4_000_000, currency="VND")
        assert AutoReminderScheduler._money(invoice) == "6.000.000 ₫"

    def test_chua_tra_dong_nao_thi_bao_nguyen_tong(self) -> None:
        invoice = MagicMock(total=700_000, amount_paid=0, currency="VND")
        assert AutoReminderScheduler._money(invoice) == "700.000 ₫"

    def test_ngay_kieu_viet_nam(self) -> None:
        assert AutoReminderScheduler._vn_date(date(2026, 7, 5)) == "05/07/2026"


class TestSoSanhMoc:
    def test_moc_khong_co_thi_khong_tinh_la_qua_han(self) -> None:
        """Báo giá chưa gửi (`sent_at` NULL) thì không có gì để nhắc."""
        scheduler = AutoReminderScheduler(db=MagicMock())
        assert scheduler._is_older_than(None, 3) is False

    def test_du_ngay_thi_tinh(self) -> None:
        scheduler = AutoReminderScheduler(db=MagicMock())
        assert scheduler._is_older_than(datetime.now(UTC) - timedelta(days=4), 3) is True

    def test_chua_du_ngay_thi_khong_tinh(self) -> None:
        scheduler = AutoReminderScheduler(db=MagicMock())
        assert scheduler._is_older_than(datetime.now(UTC) - timedelta(days=1), 3) is False

    def test_moc_khong_co_mui_gio_van_so_sanh_duoc(self) -> None:
        """Postgres trả về datetime naive trong vài đường đọc — so sánh thẳng là
        TypeError giữa lúc worker đang chạy."""
        scheduler = AutoReminderScheduler(db=MagicMock())
        naive = (datetime.now(UTC) - timedelta(days=10)).replace(tzinfo=None)
        assert scheduler._is_older_than(naive, 3) is True
