"""Analytics application service."""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.analytics.application.milestone_money import (
    MilestoneMoney,
    MoneyTotals,
    totals,
)
from src.modules.analytics.infrastructure.repository import AnalyticsRepository
from src.modules.analytics.schemas.response import (
    AiUsageResponse,
    DashboardResponse,
    MonthlyRevenueResponse,
    PipelineStageResponse,
    RevenueResponse,
    TopClientResponse,
    WinRateResponse,
)
from src.modules.subscriptions.application.ai_usage import AiUsageService


@dataclass
class AnalyticsService:
    db: AsyncSession
    repo: AnalyticsRepository | None = None

    def __post_init__(self) -> None:
        if self.repo is None:
            self.repo = AnalyticsRepository(self.db)

    async def get_dashboard(self, user_id: uuid.UUID) -> DashboardResponse:
        total_clients, active_deals, total_revenue_raw, pending_invoices = (
            await self.repo.dashboard_counts(user_id)
        )
        total_revenue = Decimal(str(total_revenue_raw))

        return DashboardResponse(
            total_clients=total_clients,
            active_deals=active_deals,
            total_revenue=total_revenue,
            pending_invoices=pending_invoices,
        )

    async def get_revenue(
        self,
        user_id: uuid.UUID,
        period_type: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> RevenueResponse:
        invoice_side = await self.repo.revenue(user_id, from_date, to_date)
        money = await self._milestone_money(user_id)
        return RevenueResponse(
            **invoice_side,
            total_contracted=money.contracted,
            milestone_collected=money.collected,
            milestone_outstanding=money.outstanding,
            milestones_pending=money.milestones_pending,
        )

    async def _milestone_money(self, user_id: uuid.UUID) -> MoneyTotals:
        """Gộp tiền của MỌI task thu tiền — tiền đã nằm sẵn trên task, ở đây chỉ cộng.

        Bản cũ phải đọc báo giá đã chốt, chia % ra tiền rồi khớp mốc với TÊN TASK. Bỏ được cả
        ba bước từ khi có `tasks.billing_amount`, và cũng bỏ luôn nguy cơ đổi tên task là bảng
        doanh thu âm thầm coi mốc đó chưa thu.  #Huynh"""
        rows = [
            MilestoneMoney(
                label=row["label"],
                amount=Decimal(row["amount"] or 0),
                collected=row["collected"],
            )
            for row in await self.repo.milestone_rows(user_id)
        ]
        return totals(rows)

    async def get_pipeline(
        self, user_id: uuid.UUID, snapshot_date: date | None = None
    ) -> list[PipelineStageResponse]:
        return [PipelineStageResponse(**x) for x in await self.repo.pipeline(user_id)]

    async def get_revenue_monthly(
        self, user_id: uuid.UUID, months: int = 12
    ) -> list[MonthlyRevenueResponse]:
        """Doanh thu N tháng gần nhất, LIỀN MẠCH — tháng trống điền 0.

        Điền tháng trống ở đây thay vì để frontend lo: nếu chỉ trả tháng có hoá đơn thì
        biểu đồ mất cột giữa chừng, hoặc frontend phải tự dựng lại khung thời gian và dễ
        lệch (đầu/cuối tháng, năm nhảy). Trả sẵn chuỗi đầy đủ thì frontend chỉ việc vẽ.
        """
        today = date.today()
        # Ô tháng hiện tại lùi về (months-1) tháng: chỉ số tháng tuyệt đối cho phép trừ qua
        # ranh giới năm mà không sợ tràn (tháng 1 lùi 3 → tháng 10 năm trước).
        current_idx = today.year * 12 + (today.month - 1)
        start_idx = current_idx - (months - 1)
        start_year, start_month = divmod(start_idx, 12)
        since = date(start_year, start_month + 1, 1)

        raw = await self.repo.revenue_monthly(user_id, since)
        by_month = {r["month"].strftime("%Y-%m"): r for r in raw}

        result: list[MonthlyRevenueResponse] = []
        for offset in range(months):
            year, month = divmod(start_idx + offset, 12)
            key = f"{year:04d}-{month + 1:02d}"
            found = by_month.get(key)
            result.append(
                MonthlyRevenueResponse(
                    month=key,
                    invoiced=Decimal(str(found["invoiced"])) if found else Decimal(0),
                    collected=Decimal(str(found["collected"])) if found else Decimal(0),
                )
            )
        return result

    async def get_win_rate(
        self, user_id: uuid.UUID, from_date: date | None = None, to_date: date | None = None
    ) -> WinRateResponse:
        return WinRateResponse(**await self.repo.win_rate(user_id, from_date, to_date))

    async def get_top_clients(
        self,
        user_id: uuid.UUID,
        limit: int = 10,
        from_date: date | None = None,
        to_date: date | None = None,
        metric: str = "milestone_collected",
    ) -> list[TopClientResponse]:
        """Khách nào mang lại nhiều tiền nhất.

        Mặc định tính theo TIỀN MỐC (`milestone_collected`) chứ không phải hoá đơn: luồng
        chính không còn bắt lập hoá đơn, nên bản cũ join `invoices` sẽ trả về danh sách
        rỗng cho gần như mọi freelancer. Hai giá trị cũ (`total_collected`,
        `total_invoiced`) vẫn dùng được cho ai muốn nhìn theo chứng từ.  #Huynh
        """
        if metric in ("total_collected", "total_invoiced"):
            return [
                TopClientResponse(**x)
                for x in await self.repo.top_clients(user_id, limit, from_date, to_date, metric)
            ]

        # `milestone_rows` trả về MỖI TASK THU TIỀN một dòng (bản cũ: mỗi deal một dòng), nên
        # `deal_count` phải đếm deal KHÁC NHAU. Cộng thẳng 1 cho mỗi dòng là một khách có bốn
        # hạng mục bỗng thành bốn deal.  #Huynh
        by_client: dict[uuid.UUID, dict] = {}
        deals_by_client: dict[uuid.UUID, set[uuid.UUID]] = {}
        for row in await self.repo.milestone_rows(user_id):
            client_id = row["client_id"]
            entry = by_client.setdefault(
                client_id,
                {
                    "client_id": client_id,
                    "name": row["client_name"],
                    "revenue": Decimal(0),
                    "outstanding": Decimal(0),
                    "deal_count": 0,
                },
            )
            amount = Decimal(row["amount"] or 0)
            if row["collected"]:
                entry["revenue"] += amount
            else:
                entry["outstanding"] += amount
            deals_by_client.setdefault(client_id, set()).add(row["deal_id"])

        for client_id, entry in by_client.items():
            entry["deal_count"] = len(deals_by_client.get(client_id, ()))

        ranked = sorted(by_client.values(), key=lambda x: x["revenue"], reverse=True)
        return [TopClientResponse(**x) for x in ranked[:limit]]

    async def get_ai_usage(
        self, user_id: uuid.UUID, from_date: date | None = None, to_date: date | None = None
    ) -> AiUsageResponse:
        """Đã dùng bao nhiêu lượt AI, còn bao nhiêu theo gói.

        Endpoint này TRƯỚC ĐÂY LUÔN TRẢ VỀ 0: nó cộng từ bảng `usage_records`, mà không
        ai ghi vào bảng đó. Giờ `AiUsageService.consume()` ghi thật, nên con số mới có
        nghĩa — và ta bổ sung hạn mức để màn "Gói đăng ký" nói được "3/50" thay vì
        "đã dùng 3 lượt" (3 trên bao nhiêu?).  #Huynh
        """
        usage = await self.repo.ai_usage(user_id, from_date, to_date)
        quota = await AiUsageService(db=self.db).summary(user_id)

        return AiUsageResponse(
            generations_used=quota["used"],
            estimated_cost_usd=usage.get("estimated_cost_usd", 0),
            limit=quota["limit"],
            remaining=quota["remaining"],
            can_use_ai=quota["can_use_ai"],
            period_start=quota.get("period_start"),
            period_end=quota.get("period_end"),
        )
