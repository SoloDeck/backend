"""Projects and tasks application service."""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.projects.schemas.request import (
    ProjectCreateRequest,
    ProjectUpdateRequest,
    TaskCreateRequest,
    TaskUpdateRequest,
)
from src.shared.exceptions.domain import NotFoundError


@dataclass
class ProjectsService:
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

    async def _get_project(self, user_id: uuid.UUID, project_id: uuid.UUID):
        from src.infrastructure.database.models import ProjectModel

        project = await self.db.scalar(
            select(ProjectModel).where(
                ProjectModel.id == project_id,
                ProjectModel.owner_user_id == user_id,
            )
        )
        if project is None:
            raise NotFoundError(f"Project {project_id} not found")
        return project

    async def _get_task(self, user_id: uuid.UUID, project_id: uuid.UUID, task_id: uuid.UUID):
        from src.infrastructure.database.models import TaskModel

        task = await self.db.scalar(
            select(TaskModel).where(
                TaskModel.id == task_id,
                TaskModel.project_id == project_id,
                TaskModel.owner_user_id == user_id,
            )
        )
        if task is None:
            raise NotFoundError(f"Task {task_id} not found")
        return task

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------

    async def create_project(self, user_id: uuid.UUID, payload: ProjectCreateRequest):
        from src.infrastructure.database.models import ProjectModel

        await self._get_deal(user_id, payload.deal_id)
        project = ProjectModel(
            deal_id=payload.deal_id,
            owner_user_id=user_id,
            title=payload.title,
            description=payload.description,
        )
        self.db.add(project)
        await self.db.flush()
        await self.db.refresh(project)
        return project

    async def list_projects(self, user_id: uuid.UUID, deal_id: uuid.UUID | None = None):
        from src.infrastructure.database.models import ProjectModel

        conditions = [ProjectModel.owner_user_id == user_id]
        if deal_id is not None:
            conditions.append(ProjectModel.deal_id == deal_id)

        result = await self.db.execute(
            select(ProjectModel).where(*conditions).order_by(ProjectModel.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_project(self, user_id: uuid.UUID, project_id: uuid.UUID):
        return await self._get_project(user_id, project_id)

    async def update_project(self, user_id: uuid.UUID, project_id: uuid.UUID, payload: ProjectUpdateRequest):
        project = await self._get_project(user_id, project_id)
        for field in payload.model_fields_set:
            setattr(project, field, getattr(payload, field))
        await self.db.flush()
        await self.db.refresh(project)
        return project

    async def delete_project(self, user_id: uuid.UUID, project_id: uuid.UUID) -> None:
        project = await self._get_project(user_id, project_id)
        await self.db.delete(project)
        await self.db.flush()

    # ------------------------------------------------------------------
    # Tasks
    # ------------------------------------------------------------------

    async def list_tasks(self, user_id: uuid.UUID, project_id: uuid.UUID):
        from src.infrastructure.database.models import TaskModel

        await self._get_project(user_id, project_id)
        result = await self.db.execute(
            select(TaskModel)
            .where(TaskModel.project_id == project_id, TaskModel.owner_user_id == user_id)
            .order_by(TaskModel.is_done.asc(), TaskModel.created_at.asc())
        )
        tasks = list(result.scalars().all())
        total = len(tasks)
        done = sum(1 for t in tasks if t.is_done)
        percent = round(done / total * 100) if total > 0 else 0
        return tasks, total, done, percent

    async def create_task(self, user_id: uuid.UUID, project_id: uuid.UUID, payload: TaskCreateRequest):
        from src.infrastructure.database.models import TaskModel

        await self._get_project(user_id, project_id)
        task = TaskModel(
            project_id=project_id,
            owner_user_id=user_id,
            title=payload.title,
            note=payload.note,
        )
        self.db.add(task)
        await self.db.flush()
        await self.db.refresh(task)
        return task

    async def update_task(
        self, user_id: uuid.UUID, project_id: uuid.UUID, task_id: uuid.UUID, payload: TaskUpdateRequest
    ):
        task = await self._get_task(user_id, project_id, task_id)
        for field in payload.model_fields_set:
            setattr(task, field, getattr(payload, field))
        await self.db.flush()
        await self.db.refresh(task)
        return task

    async def delete_task(self, user_id: uuid.UUID, project_id: uuid.UUID, task_id: uuid.UUID) -> None:
        task = await self._get_task(user_id, project_id, task_id)
        await self.db.delete(task)
        await self.db.flush()
