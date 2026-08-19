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
    TaskModel,
    UsageRecordModel,
)


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
        """Mỗi TASK THU TIỀN một dòng:
        `{deal_id, client_id, client_name, label, amount, collected}`.

        Tập deal được tính là **deal ĐÃ CÓ TASK THU TIỀN**, không lọc theo giai đoạn. Task thu
        tiền sinh ra lúc GHI NHẬN HỢP ĐỒNG ĐÃ KÝ, còn deal chỉ vào `active` khi freelancer bấm
        "Bắt đầu triển khai" — hai việc tách nhau. Lọc theo `stage` thì deal đã ký mà chưa bấm
        triển khai bị bỏ ra ngoài, và bảng lại thiếu tiền đúng như lỗi đang phải sửa (đã bắt
        được bằng test tích hợp, không phải đoán).

        Đòi `billing_amount IS NOT NULL` chứ KHÔNG rơi về tiền tố tên: task cũ mà migration
        `a4b5c6d7e8f9` cố ý không backfill (tên đã sửa, tổng lệch giá deal) thì để nó vắng mặt
        ở đây — cộng nửa vời vào bảng tiền còn tệ hơn thiếu hẳn, vì con số trông vẫn có vẻ đúng.
        Guard "hoàn thành dự án" vẫn bắt được chúng qua lối rơi về theo tiền tố.

        Không còn phải đọc báo giá: tiền nằm sẵn trên task. Bản cũ phải tra `proposals.content`
        rồi chia % và khớp mốc với TÊN TASK — bớt được hẳn một truy vấn và cả một lớp phép tính.

        Tách vài truy vấn nhỏ thay vì một join lớn: một freelancer có vài chục deal, ghép trong
        Python rẻ hơn nhiều so với công sức đọc lại một câu SQL bốn tầng sau này. Mỗi truy vấn
        đều lọc theo chủ sở hữu, không dựa vào join để chặn rò dữ liệu.  #Huynh
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
                select(
                    TaskModel.entity_id,
                    TaskModel.title,
                    TaskModel.status,
                    TaskModel.billing_amount,
                ).where(
                    TaskModel.entity_type == "project",
                    TaskModel.entity_id.in_(list(deal_by_project.keys())),
                    TaskModel.billing_amount.is_not(None),
                )
            )
        ).all()
        if not tasks:
            return []

        deal_ids = {
            deal_by_project[project_id]
            for project_id, _, _, _ in tasks
            if project_id in deal_by_project
        }

        deals = (
            await self.db.execute(
                select(DealModel.id, DealModel.client_id, ClientModel.name)
                .join(ClientModel, ClientModel.id == DealModel.client_id)
                .where(
                    DealModel.owner_user_id == owner_user_id,
                    DealModel.deleted_at.is_(None),
                    DealModel.id.in_(list(deal_ids)),
                )
            )
        ).all()
        client_by_deal = {row[0]: (row[1], row[2]) for row in deals}
        if not client_by_deal:
            return []

        rows: list[dict] = []
        for project_id, title, status, amount in tasks:
            deal_id = deal_by_project.get(project_id)
            client = client_by_deal.get(deal_id) if deal_id else None
            if client is None:
                continue  # deal đã xoá mềm hoặc không thuộc chủ này
            rows.append(
                {
                    "deal_id": deal_id,
                    "client_id": client[0],
                    "client_name": client[1],
                    "label": title,
                    "amount": amount,
                    "collected": status == "done",
                }
            )
        return rows

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
