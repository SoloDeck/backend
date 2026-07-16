"""AI Jobs application service."""

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import AiJobModel
from src.modules.ai_jobs.domain.value_objects.status import AiJobStatus, can_transition
from src.modules.ai_jobs.infrastructure.repository import AiJobsRepository
from src.modules.ai_jobs.schemas.request import CreateAiJobRequest
from src.shared.exceptions.domain import (
    BusinessRuleError,
    InvalidStateTransitionError,
    NotFoundError,
)

# Which entity_type a job type is allowed to target. proposal_generator
# targets the source deal (it creates a new proposal); contract_generator
# targets an existing draft contract (it fills in content, doesn't create one).
_EXPECTED_ENTITY_TYPE: dict[str, str] = {
    "lead_qualifier": "deal",
    "proposal_generator": "deal",
    "contract_generator": "contract",
}


@dataclass
class AiJobsService:
    db: AsyncSession
    repo: AiJobsRepository | None = None

    def __post_init__(self) -> None:
        if self.repo is None:
            self.repo = AiJobsRepository(self.db)

    async def create_job(
        self, owner_user_id: uuid.UUID, payload: CreateAiJobRequest
    ) -> AiJobModel:
        expected_entity_type = _EXPECTED_ENTITY_TYPE[payload.type]
        if payload.entity_type != expected_entity_type:
            raise BusinessRuleError(
                f"'{payload.type}' jobs must target entity_type "
                f"'{expected_entity_type}', got '{payload.entity_type}'"
            )

        await self._verify_entity_exists(owner_user_id, payload.entity_type, payload.entity_id)

        if payload.idempotency_key:
            existing = await self.repo.get_by_idempotency_key(
                owner_user_id, payload.idempotency_key
            )
            if existing is not None:
                return existing

        existing_active = await self.repo.get_active_job(
            owner_user_id, payload.entity_type, payload.entity_id, payload.type
        )
        if existing_active is not None:
            return existing_active

        job = await self.repo.create(
            owner_user_id=owner_user_id,
            type=payload.type,
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
            idempotency_key=payload.idempotency_key,
        )

        # The Celery worker opens its own DB connection and must see this row
        # — commit now rather than waiting for the request's implicit commit,
        # otherwise the worker can query the job before it's visible. Refresh
        # afterward since commit() expires attributes in some session configs
        # (e.g. the test harness), and both _dispatch and the router read
        # job's attributes right after this.
        await self.db.commit()
        await self.db.refresh(job)
        self._dispatch(job)
        return job

    async def get_job(self, owner_user_id: uuid.UUID, job_id: uuid.UUID) -> AiJobModel:
        job = await self.repo.get_by_id_for_owner(job_id, owner_user_id)
        if job is None:
            raise NotFoundError(f"AI job {job_id} not found")
        return job

    async def list_jobs(
        self,
        owner_user_id: uuid.UUID,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[AiJobModel], int]:
        return await self.repo.list_all(
            owner_user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            page=page,
            page_size=page_size,
        )

    async def cancel_job(self, owner_user_id: uuid.UUID, job_id: uuid.UUID) -> AiJobModel:
        job = await self.repo.get_by_id_for_owner(job_id, owner_user_id)
        if job is None:
            raise NotFoundError(f"AI job {job_id} not found")

        current = AiJobStatus(job.status)
        if not can_transition(current, AiJobStatus.CANCELLED):
            raise InvalidStateTransitionError("ai_job", current.value, AiJobStatus.CANCELLED.value)

        # Best-effort: if the worker is mid-LLM-call, this only flags intent —
        # the task checks this flag before writing its own terminal status
        # and skips overwriting it (see src/workers/ai_jobs/tasks.py).
        return await self.repo.mark_cancelled(job)

    async def _verify_entity_exists(
        self, owner_user_id: uuid.UUID, entity_type: str, entity_id: uuid.UUID
    ) -> None:
        if entity_type == "deal":
            deal = await self.repo.get_deal(entity_id, owner_user_id)
            if deal is None:
                raise NotFoundError(f"Deal {entity_id} not found")
        elif entity_type == "contract":
            contract = await self.repo.get_contract(entity_id, owner_user_id)
            if contract is None:
                raise NotFoundError(f"Contract {entity_id} not found")

    def _dispatch(self, job: AiJobModel) -> None:
        from src.workers.ai_jobs.tasks import (
            generate_contract_async,
            generate_proposal_async,
            qualify_deal_async_by_job_id,
        )

        task_by_type = {
            "lead_qualifier": qualify_deal_async_by_job_id,
            "proposal_generator": generate_proposal_async,
            "contract_generator": generate_contract_async,
        }
        task_by_type[job.type].delay(str(job.id))
