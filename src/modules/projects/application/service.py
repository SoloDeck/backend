"""Projects application service.

Owns all business rules for project lifecycle. A project is always scoped to its
`owner_id`; cross-tenant access raises NotFoundError (never leaks existence).
"""

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import ProjectModel
from src.modules.projects.infrastructure.repository import ProjectRepository
from src.modules.projects.schemas.request import CreateProjectRequest, UpdateProjectRequest
from src.shared.exceptions.domain import NotFoundError


@dataclass
class ProjectService:
    db: AsyncSession
    repo: ProjectRepository = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.repo is None:
            self.repo = ProjectRepository(self.db)

    async def _get(self, project_id: uuid.UUID, owner_user_id: uuid.UUID) -> ProjectModel:
        project = await self.repo.get_by_id(project_id, owner_user_id)
        if project is None:
            raise NotFoundError(f"Project {project_id} not found")
        return project

    async def create(self, owner_user_id: uuid.UUID, payload: CreateProjectRequest) -> ProjectModel:
        return await self.repo.create(
            owner_id=owner_user_id,
            deal_id=payload.deal_id,
            name=payload.name,
            description=payload.description,
            start_date=payload.start_date,
            end_date=payload.end_date,
        )

    async def list(
        self,
        owner_user_id: uuid.UUID,
        deal_id: uuid.UUID | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ProjectModel], int]:
        offset = (page - 1) * page_size
        return await self.repo.list(
            owner_user_id,
            deal_id=deal_id,
            status=status,
            offset=offset,
            limit=page_size,
        )

    async def get(self, project_id: uuid.UUID, owner_user_id: uuid.UUID) -> ProjectModel:
        return await self._get(project_id, owner_user_id)

    async def update(
        self, project_id: uuid.UUID, owner_user_id: uuid.UUID, payload: UpdateProjectRequest
    ) -> ProjectModel:
        project = await self._get(project_id, owner_user_id)
        data = payload.model_dump(exclude_unset=True)
        for field, value in data.items():
            setattr(project, field, value)
        return await self.repo.save(project)

    async def delete(self, project_id: uuid.UUID, owner_user_id: uuid.UUID) -> None:
        project = await self._get(project_id, owner_user_id)
        await self.repo.delete(project)

    async def get_or_create_for_deal(
        self, deal_id: uuid.UUID, owner_user_id: uuid.UUID, name: str | None = None
    ) -> ProjectModel:
        """Return the existing project for a deal, or create one (status=planning).

        Idempotent entry point used when a Deal transitions to the `active` stage
        (see DealsService.transition_stage). Kept here — rather than duplicating
        creation logic in the deals module — so project invariants stay owned by
        the projects domain.
        """
        existing = await self.repo.get_by_deal_id(deal_id, owner_user_id)
        if existing is not None:
            return existing
        return await self.repo.create(
            owner_id=owner_user_id,
            deal_id=deal_id,
            name=name or f"Project for deal {deal_id}",
            description=None,
            start_date=None,
            end_date=None,
        )
