"""Tasks application service.

One service backs every polymorphic entry point (/projects/.../tasks,
/deals/.../tasks, /reminders/.../tasks). Tasks have no owner column of their own;
tenant isolation is enforced by verifying the owning entity belongs to the user
before any read or write (see TaskRepository.entity_exists_for_owner).
"""

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import ChecklistItemModel, TaskModel
from src.modules.tasks.infrastructure.repository import TaskRepository
from src.modules.tasks.schemas.request import (
    CreateChecklistItemRequest,
    CreateTaskRequest,
    UpdateChecklistItemRequest,
    UpdateTaskRequest,
)
from src.shared.exceptions.domain import NotFoundError

_DEFAULT_PRIORITY = "medium"


@dataclass
class TaskService:
    db: AsyncSession
    repo: TaskRepository = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.repo is None:
            self.repo = TaskRepository(self.db)

    async def _require_entity_owner(
        self, entity_type: str, entity_id: uuid.UUID, owner_user_id: uuid.UUID
    ) -> None:
        if not await self.repo.entity_exists_for_owner(entity_type, entity_id, owner_user_id):
            raise NotFoundError(f"{entity_type.capitalize()} {entity_id} not found")

    async def _get_owned_task(self, task_id: uuid.UUID, owner_user_id: uuid.UUID) -> TaskModel:
        task = await self.repo.get_by_id(task_id)
        if task is None:
            raise NotFoundError(f"Task {task_id} not found")
        await self._require_entity_owner(task.entity_type, task.entity_id, owner_user_id)
        return task

    # --- tasks ----------------------------------------------------------------

    async def list_by_entity(
        self,
        entity_type: str,
        entity_id: uuid.UUID,
        owner_user_id: uuid.UUID,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[TaskModel], int]:
        await self._require_entity_owner(entity_type, entity_id, owner_user_id)
        offset = (page - 1) * page_size
        return await self.repo.list_by_entity(
            entity_type, entity_id, status=status, offset=offset, limit=page_size
        )

    async def create_for_entity(
        self,
        entity_type: str,
        entity_id: uuid.UUID,
        owner_user_id: uuid.UUID,
        payload: CreateTaskRequest,
    ) -> TaskModel:
        await self._require_entity_owner(entity_type, entity_id, owner_user_id)
        return await self.repo.create(
            entity_type=entity_type,
            entity_id=entity_id,
            title=payload.title,
            description=payload.description,
            priority=payload.priority.value if payload.priority else _DEFAULT_PRIORITY,
            deadline=payload.deadline,
        )

    async def get(self, task_id: uuid.UUID, owner_user_id: uuid.UUID) -> TaskModel:
        return await self._get_owned_task(task_id, owner_user_id)

    async def update(
        self, task_id: uuid.UUID, owner_user_id: uuid.UUID, payload: UpdateTaskRequest
    ) -> TaskModel:
        task = await self._get_owned_task(task_id, owner_user_id)
        data = payload.model_dump(exclude_unset=True)
        for field, value in data.items():
            setattr(task, field, value)
        return await self.repo.save(task)

    async def delete(self, task_id: uuid.UUID, owner_user_id: uuid.UUID) -> None:
        task = await self._get_owned_task(task_id, owner_user_id)
        await self.repo.delete(task)

    # --- checklist items ------------------------------------------------------

    async def add_checklist_item(
        self,
        task_id: uuid.UUID,
        owner_user_id: uuid.UUID,
        payload: CreateChecklistItemRequest,
    ) -> ChecklistItemModel:
        await self._get_owned_task(task_id, owner_user_id)
        return await self.repo.add_checklist_item(
            task_id=task_id,
            text=payload.text,
            position=payload.position,
        )

    async def update_checklist_item(
        self,
        task_id: uuid.UUID,
        item_id: uuid.UUID,
        owner_user_id: uuid.UUID,
        payload: UpdateChecklistItemRequest,
    ) -> ChecklistItemModel:
        await self._get_owned_task(task_id, owner_user_id)
        item = await self.repo.get_checklist_item(item_id, task_id)
        if item is None:
            raise NotFoundError(f"Checklist item {item_id} not found")
        data = payload.model_dump(exclude_unset=True)
        for field, value in data.items():
            setattr(item, field, value)
        return await self.repo.save_checklist_item(item)

    async def delete_checklist_item(
        self, task_id: uuid.UUID, item_id: uuid.UUID, owner_user_id: uuid.UUID
    ) -> None:
        await self._get_owned_task(task_id, owner_user_id)
        item = await self.repo.get_checklist_item(item_id, task_id)
        if item is None:
            raise NotFoundError(f"Checklist item {item_id} not found")
        await self.repo.delete_checklist_item(item)
