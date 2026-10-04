"""Tiền của deal KHÔNG THÀNH CÔNG trong bảng doanh thu.

Khoản CHƯA thu của deal thất bại sẽ không bao giờ về nên không được tính là "còn phải thu" (cũng
không nằm trong "Tổng"); khoản ĐÃ thu thì vẫn là tiền thật. Test này đi qua `AnalyticsService` với
kho giả để kiểm đúng chỗ lọc, không cần DB.
"""

import uuid
from decimal import Decimal
from unittest.mock import MagicMock

from src.modules.analytics.application.service import AnalyticsService

SONG, HONG = uuid.uuid4(), uuid.uuid4()
KHACH_SONG, KHACH_HONG = uuid.uuid4(), uuid.uuid4()


def row(deal_id, client_id, name, amount, collected, stage):  # type: ignore[no-untyped-def]
    return {
        "deal_id": deal_id,
        "client_id": client_id,
        "client_name": name,
        "label": "mốc",
        "amount": Decimal(amount),
        "collected": collected,
        "deal_stage": stage,
    }


class FakeRepo:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows

    async def milestone_rows(self, user_id):  # type: ignore[no-untyped-def]
        return self.rows

    async def revenue(self, user_id, from_date, to_date):  # type: ignore[no-untyped-def]
        return {"total_invoiced": 0, "total_collected": 0, "total_outstanding": 0}


def service(rows: list[dict]) -> AnalyticsService:
    return AnalyticsService(db=MagicMock(), repo=FakeRepo(rows))  # type: ignore[arg-type]


ROWS = [
    row(SONG, KHACH_SONG, "Khách sống", 100, True, "active"),
    row(SONG, KHACH_SONG, "Khách sống", 100, False, "active"),
    row(HONG, KHACH_HONG, "Khách hỏng", 40, True, "lost"),  # đã cọc
    row(HONG, KHACH_HONG, "Khách hỏng", 60, False, "lost"),  # sẽ không bao giờ về
]


async def test_phan_chua_thu_cua_deal_that_bai_khong_tinh_vao_con_phai_thu() -> None:
    revenue = await service(ROWS).get_revenue(uuid.uuid4())

    assert revenue.milestone_outstanding == Decimal(100)  # chỉ khoản chưa thu của deal còn sống
    assert revenue.milestones_pending == 1


async def test_phan_da_thu_cua_deal_that_bai_van_la_tien_that() -> None:
    revenue = await service(ROWS).get_revenue(uuid.uuid4())

    assert revenue.milestone_collected == Decimal(140)  # 100 + khoản cọc 40
    assert revenue.total_contracted == Decimal(240)  # vẫn = Đã thu + Còn phải thu


async def test_trung_binh_chi_tinh_deal_con_song() -> None:
    revenue = await service(ROWS).get_revenue(uuid.uuid4())

    # 200 ÷ 1 deal; deal hỏng không kéo trung bình xuống.
    assert revenue.average_deal_value == Decimal("200.00")


async def test_bang_khach_hang_khong_ghi_no_cua_deal_that_bai() -> None:
    top = {c.name: c for c in await service(ROWS).get_top_clients(uuid.uuid4(), 10)}

    assert top["Khách hỏng"].outstanding == Decimal(0)
    assert top["Khách hỏng"].revenue == Decimal(40)  # khoản cọc vẫn tính
    assert top["Khách sống"].outstanding == Decimal(100)


async def test_dong_khong_khai_giai_doan_thi_duoc_coi_la_deal_binh_thuong() -> None:
    """Kho cũ/giả không trả `deal_stage`: không được hiểu nhầm là deal thất bại."""
    bo_khoa = [{k: v for k, v in r.items() if k != "deal_stage"} for r in ROWS]

    revenue = await service(bo_khoa).get_revenue(uuid.uuid4())

    assert revenue.milestone_outstanding == Decimal(160)  # 100 + 60: không bỏ dòng nào
