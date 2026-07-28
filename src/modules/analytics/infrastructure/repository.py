import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import (
    AiCostRecordModel,
    ClientModel,
    DealModel,
    InvoiceModel,
    ProjectModel,
    ProposalModel,
    TaskModel,
    UsageRecordModel,
)
from src.modules.tasks.application.service import PAYMENT_TASK_PREFIX


@dataclass
class AnalyticsRepository:
    db: AsyncSession

    async def dashboard_counts(self, owner_user_id: uuid.UUID) -> tuple[int, int, object, int]:
        clients = (
            await self.db.scalar(
                select(func.count())
                .select_from(ClientModel)
                .where(ClientModel.owner_user_id == owner_user_id, ClientModel.deleted_at.is_(None))
            )
            or 0
        )
        active_deals = (
            await self.db.scalar(
                select(func.count())
                .select_from(DealModel)
                .where(
                    DealModel.owner_user_id == owner_user_id,
                    DealModel.deleted_at.is_(None),
                    DealModel.stage.notin_(["completed_and_billed", "lost"]),
                )
            )
            or 0
        )
        revenue = (
            await self.db.scalar(
                select(func.sum(InvoiceModel.total)).where(
                    InvoiceModel.owner_user_id == owner_user_id, InvoiceModel.status == "paid"
                )
            )
            or 0
        )
        pending = (
            await self.db.scalar(
                select(func.count())
                .select_from(InvoiceModel)
                .where(
                    InvoiceModel.owner_user_id == owner_user_id,
                    InvoiceModel.status.in_(["draft", "sent"]),
                )
            )
            or 0
        )
        return clients, active_deals, revenue, pending

    async def revenue(
        self, owner_user_id: uuid.UUID, from_date: date | None = None, to_date: date | None = None
    ) -> dict:
        conditions = [InvoiceModel.owner_user_id == owner_user_id]
        if from_date is not None:
            conditions.append(InvoiceModel.issue_date >= from_date)
        if to_date is not None:
            conditions.append(InvoiceModel.issue_date <= to_date)
        row = (
            await self.db.execute(
                select(
                    func.coalesce(func.sum(InvoiceModel.total), 0),
                    func.coalesce(func.sum(InvoiceModel.amount_paid), 0),
                ).where(*conditions)
            )
        ).one()
        return {
            "total_invoiced": row[0],
            "total_collected": row[1],
            "total_outstanding": row[0] - row[1],
        }

    async def milestone_rows(self, owner_user_id: uuid.UUID) -> list[dict]:
        """Dữ liệu THÔ để tính tiền theo mốc thanh toán, mỗi deal một dòng.

        Trả về `{deal_id, client_id, client_name, final_price, content, done_titles}` —
        phép tính (chia % ra tiền, đối chiếu mốc với task) để tầng application lo, xem
        `application/milestone_money.py`.

        Tập deal được tính là **deal ĐÃ CÓ TASK "Thu tiền:"**, không lọc theo giai đoạn.
        Task thu tiền sinh ra lúc GHI NHẬN HỢP ĐỒNG ĐÃ KÝ, còn deal chỉ vào `active` khi
        freelancer bấm "Bắt đầu triển khai" — hai việc tách nhau. Lọc theo `stage` thì deal
        đã ký mà chưa bấm triển khai bị bỏ ra ngoài, và bảng lại thiếu tiền đúng như lỗi
        đang phải sửa (đã bắt được bằng test tích hợp, không phải đoán).

        Tách vài truy vấn nhỏ thay vì một join lớn: một freelancer có vài chục deal, ghép
        trong Python rẻ hơn nhiều so với công sức đọc lại một câu SQL bốn tầng sau này.
        Mỗi truy vấn đều lọc theo chủ sở hữu, không dựa vào join để chặn rò dữ liệu.  #Huynh
        """
        projects = (
            await self.db.execute(
                select(ProjectModel.id, ProjectModel.deal_id).where(
                    ProjectModel.owner_id == owner_user_id,
                    ProjectModel.deal_id.is_not(None),
                )
            )
        ).all()
        deal_by_project = {row[0]: row[1] for row in projects}
        if not deal_by_project:
            return []

        # Task thu tiền nằm trên PROJECT của deal, không nằm trên deal.
        # `tasks` KHÔNG có cột chủ sở hữu — quyền đi theo entity, nên lọc bằng danh sách
        # project đã xác thực chủ ở trên chứ không dựa vào join.
        tasks = (
            await self.db.execute(
                select(TaskModel.entity_id, TaskModel.title, TaskModel.status).where(
                    TaskModel.entity_type == "project",
                    TaskModel.entity_id.in_(list(deal_by_project.keys())),
                    TaskModel.title.like(f"{PAYMENT_TASK_PREFIX}%"),
                )
            )
        ).all()

        done_by_deal: dict[uuid.UUID, set[str]] = {}
        deal_ids: set[uuid.UUID] = set()
        for project_id, title, status in tasks:
            deal_id = deal_by_project.get(project_id)
            if deal_id is None:
                continue
            deal_ids.add(deal_id)
            if status == "done":
                done_by_deal.setdefault(deal_id, set()).add(title)

        if not deal_ids:
            return []

        deals = (
            await self.db.execute(
                select(
                    DealModel.id,
                    DealModel.client_id,
                    DealModel.estimated_value,
                    ClientModel.name,
                )
                .join(ClientModel, ClientModel.id == DealModel.client_id)
                .where(
                    DealModel.owner_user_id == owner_user_id,
                    DealModel.deleted_at.is_(None),
                    DealModel.id.in_(list(deal_ids)),
                )
            )
        ).all()
        if not deals:
            return []

        # Báo giá ĐÃ CHỐT của từng deal — nguồn của các mốc thanh toán.
        proposals = (
            await self.db.execute(
                select(ProposalModel.deal_id, ProposalModel.content).where(
                    ProposalModel.owner_user_id == owner_user_id,
                    ProposalModel.deal_id.in_([row[0] for row in deals]),
                    ProposalModel.status == "accepted",
                )
            )
        ).all()
        content_by_deal = {row[0]: row[1] for row in proposals}

        return [
            {
                "deal_id": deal_id,
                "client_id": client_id,
                "client_name": client_name,
                "final_price": estimated_value,
                "content": content_by_deal.get(deal_id) or {},
                "done_titles": done_by_deal.get(deal_id, set()),
            }
            for deal_id, client_id, estimated_value, client_name in deals
        ]

    async def revenue_monthly(self, owner_user_id: uuid.UUID, since: date) -> list[dict]:
        """Doanh thu gom theo tháng, tính từ `since` trở đi.

        `date_trunc('month', ...)` dồn mọi hoá đơn trong tháng về ngày đầu tháng để GROUP BY.
        Chỉ trả các tháng CÓ hoá đơn; việc điền tháng trống thành 0 để service lo — repository
        chỉ truy vấn, không dựng khung thời gian.
        """
        month = func.date_trunc("month", InvoiceModel.issue_date)
        rows = (
            await self.db.execute(
                select(
                    month.label("month"),
                    func.coalesce(func.sum(InvoiceModel.total), 0),
                    func.coalesce(func.sum(InvoiceModel.amount_paid), 0),
                )
                .where(
                    InvoiceModel.owner_user_id == owner_user_id,
                    InvoiceModel.issue_date >= since,
                )
                .group_by(month)
                .order_by(month)
            )
        ).all()
        return [{"month": r[0].date(), "invoiced": r[1], "collected": r[2]} for r in rows]

    async def pipeline(self, owner_user_id: uuid.UUID) -> list[dict]:
        rows = (
            await self.db.execute(
                select(
                    DealModel.stage,
                    func.count(DealModel.id),
                    func.coalesce(func.sum(DealModel.estimated_value), 0),
                )
                .where(DealModel.owner_user_id == owner_user_id, DealModel.deleted_at.is_(None))
                .group_by(DealModel.stage)
            )
        ).all()
        return [{"stage": r[0], "deal_count": r[1], "total_value": r[2]} for r in rows]

    async def win_rate(
        self, owner_user_id: uuid.UUID, from_date: date | None = None, to_date: date | None = None
    ) -> dict:
        conditions = [DealModel.owner_user_id == owner_user_id, DealModel.deleted_at.is_(None)]
        if from_date is not None:
            conditions.append(func.date(DealModel.closed_at) >= from_date)
        if to_date is not None:
            conditions.append(func.date(DealModel.closed_at) <= to_date)
        won = (
            await self.db.scalar(
                select(func.count())
                .select_from(DealModel)
                .where(*conditions, DealModel.stage == "completed_and_billed")
            )
            or 0
        )
        lost = (
            await self.db.scalar(
                select(func.count())
                .select_from(DealModel)
                .where(*conditions, DealModel.stage == "lost")
            )
            or 0
        )
        total = won + lost
        return {"won": won, "lost": lost, "win_rate": (won / total if total else 0)}

    async def top_clients(
        self,
        owner_user_id: uuid.UUID,
        limit: int = 10,
        from_date: date | None = None,
        to_date: date | None = None,
        metric: str = "total_collected",
    ) -> list[dict]:
        amount_expr = InvoiceModel.total if metric == "total_invoiced" else InvoiceModel.amount_paid
        conditions = [
            ClientModel.owner_user_id == owner_user_id,
            InvoiceModel.owner_user_id == owner_user_id,
            ClientModel.deleted_at.is_(None),
        ]
        if from_date is not None:
            conditions.append(InvoiceModel.issue_date >= from_date)
        if to_date is not None:
            conditions.append(InvoiceModel.issue_date <= to_date)
        rows = (
            await self.db.execute(
                select(
                    ClientModel.id,
                    ClientModel.name,
                    func.coalesce(func.sum(amount_expr), 0).label("revenue"),
                )
                .join(InvoiceModel, InvoiceModel.client_id == ClientModel.id)
                .where(*conditions)
                .group_by(ClientModel.id, ClientModel.name)
                .order_by(func.coalesce(func.sum(amount_expr), 0).desc())
                .limit(limit)
            )
        ).all()
        return [{"client_id": r[0], "name": r[1], "revenue": r[2]} for r in rows]

    async def ai_usage(
        self, owner_user_id: uuid.UUID, from_date: date | None = None, to_date: date | None = None
    ) -> dict:
        conditions = [AiCostRecordModel.user_id == owner_user_id]
        if from_date is not None:
            conditions.append(func.date(AiCostRecordModel.occurred_at) >= from_date)
        if to_date is not None:
            conditions.append(func.date(AiCostRecordModel.occurred_at) <= to_date)
        cost = (
            await self.db.scalar(
                select(func.coalesce(func.sum(AiCostRecordModel.estimated_cost_usd), 0)).where(
                    *conditions
                )
            )
            or 0
        )
        generations = (
            await self.db.scalar(
                select(func.coalesce(func.sum(UsageRecordModel.ai_generations_used), 0)).where(
                    UsageRecordModel.user_id == owner_user_id
                )
            )
            or 0
        )
        return {"generations_used": generations, "estimated_cost_usd": cost}
