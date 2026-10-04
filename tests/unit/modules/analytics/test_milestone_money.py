"""Cộng tiền từ các TASK THU TIỀN — nguồn số liệu của bảng doanh thu.

Vì sao có bộ này: bảng doanh thu vốn chỉ đếm hoá đơn, mà luồng chính không bắt lập hoá đơn.
Đo trên bản chạy thật: phễu hiện 7 deal đang triển khai trị giá 1,24 tỷ, bảng doanh thu ghi
"Còn phải thu: 0 đ". Đây là phép tính thay thế nó, nên phải chặt.

Phần CHIA % ra tiền đã chuyển sang `proposals/application/service.py` (lối rơi về cho báo giá
cũ) — test của nó nằm ở `tests/unit/modules/proposals/test_payment_milestones.py`. Ở đây tiền
đã nằm sẵn trên task, chỉ còn cộng.
"""

import uuid
from decimal import Decimal

from src.modules.analytics.application.milestone_money import MilestoneMoney, totals

_PRICE = Decimal(100_000_000)


class TestCongTien:
    def test_task_da_tick_thi_tinh_la_da_thu(self) -> None:
        money = totals(
            [
                MilestoneMoney(label="Đặt cọc", amount=Decimal(50_000_000), collected=True),
                MilestoneMoney(label="Bàn giao", amount=Decimal(50_000_000), collected=False),
            ]
        )
        assert money.collected == Decimal(50_000_000)
        assert money.outstanding == Decimal(50_000_000)
        assert money.contracted == _PRICE
        assert money.milestones_pending == 1

    def test_chua_tick_cai_nao_thi_con_phai_thu_bang_tong(self) -> None:
        money = totals(
            [
                MilestoneMoney(label="A", amount=Decimal(30_000_000), collected=False),
                MilestoneMoney(label="B", amount=Decimal(70_000_000), collected=False),
            ]
        )
        assert money.collected == Decimal(0)
        assert money.outstanding == _PRICE
        assert money.milestones_pending == 2

    def test_khong_co_task_thu_tien_nao_thi_khong_tinh_dong_nao(self) -> None:
        money = totals([])
        assert money.contracted == Decimal(0)
        assert money.outstanding == Decimal(0)
        assert money.milestones_pending == 0

    def test_doi_ten_task_khong_con_lam_mat_tien_khoi_bang(self) -> None:
        """Chốt lại điểm chính của cả thay đổi.

        Bản cũ khớp mốc với TÊN TASK, nên freelancer sửa tên một chữ là mốc đó thành "chưa
        thu" vĩnh viễn — hỏng im lặng. Giờ tiền đi theo cột `billing_amount`, tên chỉ còn là
        nhãn hiển thị, nên đổi tên không ảnh hưởng gì tới con số.
        """
        money = totals(
            [MilestoneMoney(label="một cái tên khác hẳn", amount=_PRICE, collected=True)]
        )
        assert money.collected == _PRICE


class TestSoDealDaKy:
    """Thẻ "Tổng" ghi "N deal đã ký": N phải là số DEAL, không phải số mốc, và phải cùng
    phạm vi với số tiền (kể cả deal đã hoàn thành — tiền của nó vẫn nằm trong tổng)."""

    def test_mot_deal_nhieu_moc_chi_tinh_mot(self) -> None:
        deal = uuid.uuid4()
        money = totals(
            [
                MilestoneMoney("Đặt cọc", Decimal(50_000_000), True, deal_id=deal),
                MilestoneMoney("Bàn giao", Decimal(50_000_000), False, deal_id=deal),
            ]
        )
        assert money.signed_deals == 1
        assert money.contracted == _PRICE

    def test_nhieu_deal_khac_nhau_thi_dem_du(self) -> None:
        a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        money = totals(
            [
                MilestoneMoney("A1", Decimal(10), True, deal_id=a),
                MilestoneMoney("A2", Decimal(10), True, deal_id=a),
                MilestoneMoney("B1", Decimal(10), False, deal_id=b),
                MilestoneMoney("C1", Decimal(10), True, deal_id=c),
            ]
        )
        assert money.signed_deals == 3

    def test_khong_co_mot_nao_thi_bang_khong(self) -> None:
        assert totals([]).signed_deals == 0

    def test_nguoi_goi_khong_khai_deal_thi_khong_tinh(self) -> None:
        """Chỗ chỉ cần cộng tiền (vd khối thanh toán của lời nhắc) không phải khai deal."""
        money = totals([MilestoneMoney("A", Decimal(10), False)])
        assert money.signed_deals == 0
        assert money.outstanding == Decimal(10)


class TestGiaTriTrungBinhMoiDeal:
    """Thẻ "Giá trị deal trung bình" = tiền các mốc ÷ số deal đã chốt. Deal không thành công không
    tham gia: một khoản cọc lẻ của deal đổ vỡ sẽ kéo trung bình xuống vô lý."""

    def test_chia_tien_cac_moc_cho_so_deal(self) -> None:
        a, b = uuid.uuid4(), uuid.uuid4()
        money = totals(
            [
                MilestoneMoney("A1", Decimal(100_000_000), True, deal_id=a),
                MilestoneMoney("A2", Decimal(50_000_000), False, deal_id=a),
                MilestoneMoney("B1", Decimal(30_000_000), False, deal_id=b),
            ]
        )
        assert money.average_deal_value == Decimal("90000000.00")  # (150 + 30) triệu ÷ 2 deal

    def test_deal_that_bai_khong_tham_gia_trung_binh(self) -> None:
        song, hong = uuid.uuid4(), uuid.uuid4()
        money = totals(
            [
                MilestoneMoney("S1", Decimal(200_000_000), True, deal_id=song),
                MilestoneMoney("H1", Decimal(10_000_000), True, deal_id=hong, lost=True),
            ]
        )
        assert money.average_deal_value == Decimal("200000000.00")
        # Nhưng khoản cọc ĐÃ thu của deal hỏng vẫn là tiền thật, nằm trong tổng.
        assert money.collected == Decimal(210_000_000)
        assert money.signed_deals == 2

    def test_toan_deal_that_bai_thi_trung_binh_bang_khong(self) -> None:
        money = totals([MilestoneMoney("H1", Decimal(10), True, deal_id=uuid.uuid4(), lost=True)])
        assert money.average_deal_value == Decimal(0)

    def test_khong_co_mot_nao_thi_bang_khong(self) -> None:
        assert totals([]).average_deal_value == Decimal(0)

    def test_nguoi_goi_khong_khai_deal_thi_khong_co_trung_binh(self) -> None:
        assert totals([MilestoneMoney("A", Decimal(10), True)]).average_deal_value == Decimal(0)

    def test_lam_tron_den_dong_le_hai_chu_so(self) -> None:
        a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        moc = [
            MilestoneMoney(x, Decimal(100), False, deal_id=d)
            for x, d in zip("abc", (a, b, c), strict=True)
        ]
        money = totals([*moc, MilestoneMoney("a2", Decimal(1), False, deal_id=a)])
        assert money.average_deal_value == Decimal("100.33")  # 301 ÷ 3
