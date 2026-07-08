import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import AiJobModel, ContractModel, DealModel
from src.modules.ai_jobs.domain.value_objects.job_error import JobError
from src.modules.ai_jobs.domain.value_objects.status import TERMINAL_STATUSES, AiJobStatus


@dataclass
class AiJobsRepository:
    db: AsyncSession

    async def get_by_id(self, job_id: uuid.UUID) -> AiJobModel | None:
        result: AiJobModel | None = await self.db.scalar(
            select(AiJobModel).where(AiJobModel.id == job_id)
        )
        return result

    async def get_by_id_for_owner(
        self, job_id: uuid.UUID, owner_user_id: uuid.UUID
    ) -> AiJobModel | None:
        result: AiJobModel | None = await self.db.scalar(
            select(AiJobModel).where(
                AiJobModel.id == job_id, AiJobModel.owner_user_id == owner_user_id
            )
        )
        return result

    async def get_by_idempotency_key(
        self, owner_user_id: uuid.UUID, idempotency_key: str
    ) -> AiJobModel | None:
        result: AiJobModel | None = await self.db.scalar(
            select(AiJobModel).where(
                AiJobModel.owner_user_id == owner_user_id,
                AiJobModel.idempotency_key == idempotency_key,
            )
        )
        return result

    async def get_active_job(
        self,
        owner_user_id: uuid.UUID,
        entity_type: str,
        entity_id: uuid.UUID,
        job_type: str,
    ) -> AiJobModel | None:
        terminal_values = [s.value for s in TERMINAL_STATUSES]
        result: AiJobModel | None = await self.db.scalar(
            select(AiJobModel)
            .where(
                AiJobModel.owner_user_id == owner_user_id,
                AiJobModel.entity_type == entity_type,
                AiJobModel.entity_id == entity_id,
                AiJobModel.type == job_type,
                AiJobModel.status.not_in(terminal_values),
            )
            .order_by(AiJobModel.created_at.desc())
        )
        return result

    async def list_all(
        self,
        owner_user_id: uuid.UUID,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[AiJobModel], int]:
        conditions = [AiJobModel.owner_user_id == owner_user_id]
        if entity_type is not None:
            conditions.append(AiJobModel.entity_type == entity_type)
        if entity_id is not None:
            conditions.append(AiJobModel.entity_id == entity_id)

        total = (
            await self.db.scalar(select(func.count()).select_from(AiJobModel).where(*conditions))
            or 0
        )
        offset = (page - 1) * page_size
        result = await self.db.execute(
            select(AiJobModel)
            .where(*conditions)
            .order_by(AiJobModel.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        return list(result.scalars().all()), total

    async def get_deal(self, deal_id: uuid.UUID, owner_user_id: uuid.UUID) -> DealModel | None:
        result: DealModel | None = await self.db.scalar(
            select(DealModel).where(
                DealModel.id == deal_id,
                DealModel.owner_user_id == owner_user_id,
                DealModel.deleted_at.is_(None),
            )
        )
        return result

    async def get_contract(
        self, contract_id: uuid.UUID, owner_user_id: uuid.UUID
    ) -> ContractModel | None:
        result: ContractModel | None = await self.db.scalar(
            select(ContractModel).where(
                ContractModel.id == contract_id,
                ContractModel.owner_user_id == owner_user_id,
            )
        )
        return result

    async def create(self, **values: object) -> AiJobModel:
        job = AiJobModel(**values)
        self.db.add(job)
        await self.db.flush()
        await self.db.refresh(job)
        return job

    async def mark_running(self, job: AiJobModel) -> AiJobModel:
        job.status = AiJobStatus.RUNNING.value
        return await self._save(job)

    async def mark_succeeded(self, job: AiJobModel, result: dict[str, object]) -> AiJobModel:
        job.status = AiJobStatus.SUCCEEDED.value
        job.result = result
        return await self._save(job)

    async def mark_failed(self, job: AiJobModel, error: JobError) -> AiJobModel:
        job.status = AiJobStatus.FAILED.value
        job.error = error.to_dict()
        return await self._save(job)

    async def mark_cancelled(self, job: AiJobModel) -> AiJobModel:
        job.status = AiJobStatus.CANCELLED.value
        return await self._save(job)

    async def refresh(self, job: AiJobModel) -> AiJobModel:
        """Reload job's current DB state — used by workers to notice a
        cancellation requested by a concurrent API call mid-run."""
        await self.db.refresh(job)
        return job

    async def _save(self, job: AiJobModel) -> AiJobModel:
        await self.db.flush()
        await self.db.refresh(job)
        return job
