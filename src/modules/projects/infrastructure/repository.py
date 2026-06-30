import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import ProjectModel


@dataclass
class ProjectRepository:
    db: AsyncSession

    async def create(self, **values: object) -> ProjectModel:
        project = ProjectModel(**values)
        self.db.add(project)
        await self.db.flush()
        await self.db.refresh(project)
        return project

    async def get_by_id(
        self, project_id: uuid.UUID, owner_user_id: uuid.UUID
    ) -> ProjectModel | None:
        res = await self.db.scalar(
            select(ProjectModel).where(
                ProjectModel.id == project_id,
                ProjectModel.owner_id == owner_user_id,
            )
        )
        return res

    async def get_by_deal_id(
        self, deal_id: uuid.UUID, owner_user_id: uuid.UUID
    ) -> ProjectModel | None:
        res = await self.db.scalar(
            select(ProjectModel)
            .where(
                ProjectModel.deal_id == deal_id,
                ProjectModel.owner_id == owner_user_id,
            )
            .order_by(ProjectModel.created_at.asc())
            .limit(1)
        )
        return res

    async def list(
        self,
        owner_user_id: uuid.UUID,
        deal_id: uuid.UUID | None,
        status: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[ProjectModel], int]:
        conditions = [ProjectModel.owner_id == owner_user_id]
        if deal_id is not None:
            conditions.append(ProjectModel.deal_id == deal_id)
        if status is not None:
            conditions.append(ProjectModel.status == status)

        total = await self.db.scalar(
            select(func.count()).select_from(ProjectModel).where(*conditions)
        )
        result = await self.db.execute(
            select(ProjectModel)
            .where(*conditions)
            .order_by(ProjectModel.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), int(total or 0)

    async def save(self, project: ProjectModel) -> ProjectModel:
        await self.db.flush()
        await self.db.refresh(project)
        return project

    async def delete(self, project: ProjectModel) -> None:
        await self.db.delete(project)
        await self.db.flush()
