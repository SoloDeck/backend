"""Tiền theo MỐC THANH TOÁN — nguồn số liệu mới của bảng doanh thu.

Vì sao có bộ này: bảng doanh thu vốn chỉ đếm hoá đơn, mà luồng chính từ Phase B không còn
bắt lập hoá đơn. Đo trên bản chạy thật: phễu hiện 7 deal đang triển khai trị giá 1,24 tỷ,
bảng doanh thu ghi "Còn phải thu: 0 đ". Đây là những phép tính thay thế nó, nên phải chặt.
"""

from decimal import Decimal

from src.ai.proposal_generator.schemas.proposal_document import PaymentMilestone
from src.modules.analytics.application.milestone_money import (
    milestone_money_for_deal,
    split_milestone_amounts,
    task_title_for,
    totals,
)

_PRICE = Decimal(100_000_000)


def _m(label: str, percent: int | None = None) -> PaymentMilestone:
    return PaymentMilestone(label=label, percent=percent)


class TestChiaTien:
    def test_theo_phan_tram(self) -> None:
        amounts = split_milestone_amounts([_m("Cọc", 30), _m("Bàn giao", 70)], _PRICE)
        assert amounts == [Decimal(30_000_000), Decimal(70_000_000)]

    def test_moc_khong_khai_phan_tram_thi_chia_deu_phan_con_lai(self) -> None:
        # Hợp đồng thật hay ghi "50% khi ký, phần còn lại khi bàn giao". Bỏ qua mốc không có
        # % là mất tiền khỏi bảng mà không ai biết.
        amounts = split_milestone_amounts([_m("Cọc", 50), _m("Còn lại")], _PRICE)
        assert amounts == [Decimal(50_000_000), Decimal(50_000_000)]

    def test_tong_cac_moc_khop_tuyet_doi_voi_gia_chot(self) -> None:
        # 3 mốc 33/33/34 chia 100 triệu — làm tròn không được phép làm bay mất đồng nào.
        amounts = split_milestone_amounts([_m("A", 33), _m("B", 33), _m("C", 34)], _PRICE)
        assert sum(amounts) == _PRICE

    def test_hop_dong_ghi_sai_tong_thi_khong_tu_sua(self) -> None:
        # Báo giá cũ lỡ ghi 50+50+30 = 130% thì bảng phải phản ánh đúng thứ đã ký; tự ép về
        # 100% là giấu lỗi, freelancer không bao giờ phát hiện ra.
        amounts = split_milestone_amounts([_m("A", 50), _m("B", 50), _m("C", 30)], _PRICE)
        assert sum(amounts) == Decimal(130_000_000)

    def test_chua_chot_gia_thi_khong_ra_tien(self) -> None:
        assert split_milestone_amounts([_m("Cọc", 50)], Decimal(0)) == [Decimal(0)]


class TestDaThuChua:
    def test_moc_co_task_da_tick_thi_tinh_la_da_thu(self) -> None:
        milestones = [_m("Đặt cọc khi ký hợp đồng", 50), _m("Thanh toán khi bàn giao", 50)]
        rows = milestone_money_for_deal(
            final_price=_PRICE,
            milestones=milestones,
            done_task_titles={task_title_for("Đặt cọc khi ký hợp đồng")},
        )
        money = totals(rows)
        assert money.collected == Decimal(50_000_000)
        assert money.outstanding == Decimal(50_000_000)
        assert money.contracted == _PRICE
        assert money.milestones_pending == 1

    def test_moc_khong_tim_duoc_task_thi_coi_nhu_chua_thu(self) -> None:
        # Dữ liệu cũ / task bị đổi tên: thà báo thừa "còn phải thu" còn hơn âm thầm coi như
        # đã lấy được tiền — sai kiểu sau khiến freelancer quên đi đòi.
        rows = milestone_money_for_deal(
            final_price=_PRICE,
            milestones=[_m("Đặt cọc", 50), _m("Bàn giao", 50)],
            done_task_titles={"Thu tiền: một cái tên khác hẳn"},
        )
        money = totals(rows)
        assert money.collected == Decimal(0)
        assert money.outstanding == _PRICE

    def test_ten_task_khop_tuyet_doi_voi_bo_sinh_task(self) -> None:
        # Nếu tiền tố này lệch với `_milestones_to_payloads` bên proposals thì mọi mốc đều
        # thành "chưa thu" vĩnh viễn — hỏng im lặng, nên chốt lại bằng test.
        assert task_title_for("Đặt cọc") == "Thu tiền: Đặt cọc"

    def test_khong_co_moc_nao_thi_khong_tinh_dong_nao(self) -> None:
        money = totals(
            milestone_money_for_deal(final_price=_PRICE, milestones=[], done_task_titles=set())
        )
        assert money.contracted == Decimal(0)
        assert money.outstanding == Decimal(0)
