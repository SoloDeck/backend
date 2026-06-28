import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import (
    ChecklistItemModel,
    DealModel,
    ProjectModel,
    ReminderModel,
    TaskModel,
)


@dataclass
class TaskRepository:
    db: AsyncSession

    async def entity_exists_for_owner(
        self, entity_type: str, entity_id: uuid.UUID, owner_user_id: uuid.UUID
    ) -> bool:
        """Verify the polymorphic parent entity exists and belongs to the user.

        There is no FK on tasks.entity_id, so tenant isolation is enforced here by
        checking the owning project / deal / reminder.
        """
        if entity_type == "project":
            stmt = select(ProjectModel.id).where(
                ProjectModel.id == entity_id,
                ProjectModel.owner_id == owner_user_id,
            )
        elif entity_type == "deal":
            stmt = select(DealModel.id).where(
                DealModel.id == entity_id,
                DealModel.owner_user_id == owner_user_id,
                DealModel.deleted_at.is_(None),
            )
        elif entity_type == "reminder":
            stmt = select(ReminderModel.id).where(
                ReminderModel.id == entity_id,
                ReminderModel.owner_user_id == owner_user_id,
            )
        else:
            return False
        return await self.db.scalar(stmt) is not None

    async def create(self, **values: object) -> TaskModel:
        task = TaskModel(**values)
        self.db.add(task)
        await self.db.flush()
        await self.db.refresh(task)
        return task

    async def get_by_id(self, task_id: uuid.UUID) -> TaskModel | None:
        return await self.db.scalar(select(TaskModel).where(TaskModel.id == task_id))

    async def list_by_entity(
        self,
        entity_type: str,
        entity_id: uuid.UUID,
        status: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[TaskModel], int]:
        conditions = [
            TaskModel.entity_type == entity_type,
            TaskModel.entity_id == entity_id,
        ]
        if status is not None:
            conditions.append(TaskModel.status == status)

        total = await self.db.scalar(
            select(func.count()).select_from(TaskModel).where(*conditions)
        )
        result = await self.db.execute(
            select(TaskModel)
            .where(*conditions)
            .order_by(TaskModel.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), int(total or 0)

    async def save(self, task: TaskModel) -> TaskModel:
        await self.db.flush()
        await self.db.refresh(task)
        return task

    async def delete(self, task: TaskModel) -> None:
        await self.db.delete(task)
        await self.db.flush()

    # --- checklist items ------------------------------------------------------

    async def add_checklist_item(self, **values: object) -> ChecklistItemModel:
        item = ChecklistItemModel(**values)
        self.db.add(item)
        await self.db.flush()
        await self.db.refresh(item)
        return item

    async def get_checklist_item(
        self, item_id: uuid.UUID, task_id: uuid.UUID
    ) -> ChecklistItemModel | None:
        return await self.db.scalar(
            select(ChecklistItemModel).where(
                ChecklistItemModel.id == item_id,
                ChecklistItemModel.task_id == task_id,
            )
        )

    async def save_checklist_item(self, item: ChecklistItemModel) -> ChecklistItemModel:
        await self.db.flush()
        await self.db.refresh(item)
        return item

    async def delete_checklist_item(self, item: ChecklistItemModel) -> None:
        await self.db.delete(item)
        await self.db.flush()
