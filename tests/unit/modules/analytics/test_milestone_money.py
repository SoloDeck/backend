"""Cộng tiền từ các TASK THU TIỀN — nguồn số liệu của bảng doanh thu.

Vì sao có bộ này: bảng doanh thu vốn chỉ đếm hoá đơn, mà luồng chính không bắt lập hoá đơn.
Đo trên bản chạy thật: phễu hiện 7 deal đang triển khai trị giá 1,24 tỷ, bảng doanh thu ghi
"Còn phải thu: 0 đ". Đây là phép tính thay thế nó, nên phải chặt.

Phần CHIA % ra tiền đã chuyển sang `proposals/application/service.py` (lối rơi về cho báo giá
cũ) — test của nó nằm ở `tests/unit/modules/proposals/test_payment_milestones.py`. Ở đây tiền
đã nằm sẵn trên task, chỉ còn cộng.
"""

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
