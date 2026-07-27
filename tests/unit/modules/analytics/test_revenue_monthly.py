"""Doanh thu theo tháng — phần điền tháng trống, chỗ dễ sai khi qua ranh giới năm."""

import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

from src.modules.analytics.application.service import AnalyticsService


def make_service(rows: list[dict]) -> AnalyticsService:
    repo = AsyncMock()
    repo.revenue_monthly.return_value = rows
    return AnalyticsService(db=AsyncMock(), repo=repo)


def uuid_user() -> uuid.UUID:
    return uuid.uuid4()


class TestChuoiLienMach:
    async def test_khong_co_hoa_don_van_tra_du_N_thang(self) -> None:
        """Freelancer mới, chưa hoá đơn nào — biểu đồ vẫn phải có đủ 12 cột (số 0), không
        được trả mảng rỗng làm frontend không biết vẽ trục tháng thế nào."""
        result = await make_service([]).get_revenue_monthly(uuid_user(), months=12)

        assert len(result) == 12
        assert all(r.invoiced == Decimal(0) and r.collected == Decimal(0) for r in result)

    async def test_thang_trong_o_giua_van_xuat_hien(self) -> None:
        """Có hoá đơn tháng đầu và tháng cuối, giữa trống — cột giữa vẫn phải là 0, không
        được nhảy cóc làm biểu đồ méo."""
        service = make_service(
            [
                {"month": date(2026, 5, 1), "invoiced": Decimal(1000), "collected": Decimal(1000)},
                {"month": date(2026, 7, 1), "invoiced": Decimal(2000), "collected": Decimal(500)},
            ]
        )
        result = await service.get_revenue_monthly(uuid_user(), months=6)
        by_month = {r.month: r for r in result}

        assert len(result) == 6
        assert by_month["2026-05"].invoiced == Decimal(1000)
        assert by_month["2026-07"].collected == Decimal(500)
        # Tháng 6 không có hoá đơn nhưng vẫn có mặt với 0.
        assert "2026-06" in by_month
        assert by_month["2026-06"].invoiced == Decimal(0)

    async def test_thu_tu_thang_tang_dan(self) -> None:
        result = await make_service([]).get_revenue_monthly(uuid_user(), months=6)
        months = [r.month for r in result]
        assert months == sorted(months)

    async def test_thang_cuoi_la_thang_hien_tai(self) -> None:
        today = date.today()
        result = await make_service([]).get_revenue_monthly(uuid_user(), months=3)
        assert result[-1].month == f"{today.year:04d}-{today.month:02d}"

    async def test_lui_qua_ranh_gioi_nam(self) -> None:
        """Chỗ dễ sai nhất: lùi tháng qua đầu năm. Nếu tính bằng month-1 thô thì tháng 1
        lùi 3 tháng ra 'tháng -2' và vỡ; phải ra tháng 11 năm trước."""
        # Dù hôm nay là tháng mấy, chuỗi 14 tháng chắc chắn bắc qua ít nhất một ranh giới năm.
        result = await make_service([]).get_revenue_monthly(uuid_user(), months=14)
        years = {r.month.split("-")[0] for r in result}
        assert len(years) >= 2  # trải qua ít nhất 2 năm
        # Mọi nhãn tháng đều hợp lệ 01..12, không có 00 hay 13.
        for r in result:
            mm = int(r.month.split("-")[1])
            assert 1 <= mm <= 12
