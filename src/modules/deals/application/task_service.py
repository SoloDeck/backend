"""Deal tasks (todo list) application service."""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.deals.schemas.task import DealTaskCreateRequest, DealTaskUpdateRequest
from src.shared.exceptions.domain import NotFoundError


@dataclass
class DealTasksService:
    db: AsyncSession

    async def _get_deal(self, user_id: uuid.UUID, deal_id: uuid.UUID):
        from src.infrastructure.database.models import DealModel

        deal = await self.db.scalar(
            select(DealModel).where(
                DealModel.id == deal_id,
                DealModel.owner_user_id == user_id,
                DealModel.deleted_at.is_(None),
            )
        )
        if deal is None:
            raise NotFoundError(f"Deal {deal_id} not found")
        return deal

    async def _get_task(self, user_id: uuid.UUID, deal_id: uuid.UUID, task_id: uuid.UUID):
        from src.infrastructure.database.models import DealTaskModel

        task = await self.db.scalar(
            select(DealTaskModel).where(
                DealTaskModel.id == task_id,
                DealTaskModel.deal_id == deal_id,
                DealTaskModel.owner_user_id == user_id,
            )
        )
        if task is None:
            raise NotFoundError(f"Task {task_id} not found")
        return task

    async def list_tasks(self, user_id: uuid.UUID, deal_id: uuid.UUID):
        from src.infrastructure.database.models import DealTaskModel

        await self._get_deal(user_id, deal_id)
        result = await self.db.execute(
            select(DealTaskModel)
            .where(DealTaskModel.deal_id == deal_id, DealTaskModel.owner_user_id == user_id)
            .order_by(DealTaskModel.is_done.asc(), DealTaskModel.created_at.asc())
        )
        tasks = list(result.scalars().all())
        total = len(tasks)
        done = sum(1 for t in tasks if t.is_done)
        percent = round(done / total * 100) if total > 0 else 0
        return tasks, total, done, percent

    async def create_task(self, user_id: uuid.UUID, deal_id: uuid.UUID, payload: DealTaskCreateRequest):
        from src.infrastructure.database.models import DealTaskModel

        await self._get_deal(user_id, deal_id)
        task = DealTaskModel(
            deal_id=deal_id,
            owner_user_id=user_id,
            title=payload.title,
            note=payload.note,
        )
        self.db.add(task)
        await self.db.flush()
        await self.db.refresh(task)
        return task

    async def update_task(
        self, user_id: uuid.UUID, deal_id: uuid.UUID, task_id: uuid.UUID, payload: DealTaskUpdateRequest
    ):
        task = await self._get_task(user_id, deal_id, task_id)
        for field in payload.model_fields_set:
            setattr(task, field, getattr(payload, field))
        await self.db.flush()
        await self.db.refresh(task)
        return task

    async def delete_task(self, user_id: uuid.UUID, deal_id: uuid.UUID, task_id: uuid.UUID) -> None:
        task = await self._get_task(user_id, deal_id, task_id)
        await self.db.delete(task)
        await self.db.flush()
