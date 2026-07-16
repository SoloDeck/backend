"""Celery tasks for long-running AI generation jobs."""

import asyncio
import uuid as _uuid

import structlog

from src.infrastructure.celery.app import celery_app
from src.modules.ai_jobs.application.errors import to_job_error
from src.modules.ai_jobs.domain.value_objects.status import AiJobStatus
from src.modules.ai_jobs.infrastructure.repository import AiJobsRepository

log = structlog.get_logger()


def _should_retry(exc: Exception, *, current_retries: int, max_retries: int) -> bool:
    """An AiJob failure is retried only if it's transient and attempts remain."""
    return to_job_error(exc).retryable and current_retries < max_retries


async def _was_cancelled(jobs_repo: AiJobsRepository, job) -> bool:  # type: ignore[no-untyped-def]
    """Re-check the job's live DB status — a concurrent cancel request may
    have flipped it while this task was mid-LLM-call."""
    await jobs_repo.refresh(job)
    return bool(job.status == AiJobStatus.CANCELLED.value)


@celery_app.task(name="src.workers.ai_jobs.tasks.qualify_lead_async", bind=True)
def qualify_lead_async(self, deal_id: str, user_id: str) -> dict:  # type: ignore[misc]
    """Async lead qualification — used when qualification is triggered non-interactively."""
    # TODO: implement
    raise NotImplementedError


@celery_app.task(
    name="src.workers.ai_jobs.tasks.qualify_deal_async_by_id",
    bind=True,
    max_retries=3,
    default_retry_delay=15,
)
def qualify_deal_async_by_id(self, user_id: str, deal_id: str) -> dict:  # type: ignore[misc]
    """Run AI lead qualification for a Deal.

    Dispatched automatically after a public intake submission so the freelancer
    sees a hot/warm/cold score in their pipeline without manual action.
    Retries up to 3 times (15 s apart) on transient failures.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from src.config.settings import settings
    from src.modules.deals.application.service import DealsService
    from src.shared.dependencies.ai import get_ai_facade

    async def _run() -> dict:
        engine = create_async_engine(str(settings.database_url))
        factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
        )
        try:
            async with factory() as session:
                service = DealsService(db=session, ai_facade=get_ai_facade())
                result = await service.qualify_deal(
                    user_id=_uuid.UUID(user_id),
                    deal_id=_uuid.UUID(deal_id),
                )
                await session.commit()
                return result or {}
        finally:
            await engine.dispose()

    try:
        log.info("qualify_deal.start", user_id=user_id, deal_id=deal_id)
        result = asyncio.run(_run())
        log.info("qualify_deal.done", user_id=user_id, deal_id=deal_id)
        return result
    except Exception as exc:
        log.error("qualify_deal.failed", user_id=user_id, deal_id=deal_id, error=str(exc))
        raise self.retry(exc=exc) from exc


@celery_app.task(
    name="src.workers.ai_jobs.tasks.qualify_deal_async_by_job_id",
    bind=True,
    max_retries=3,
    default_retry_delay=15,
)
def qualify_deal_async_by_job_id(self, job_id: str) -> dict:  # type: ignore[misc]
    """Run AI lead qualification for the deal referenced by an AiJob row.

    Job-tracked counterpart to qualify_deal_async_by_id (which is fire-and-
    forget, dispatched automatically after intake submission). This variant
    is dispatched by POST /api/v1/ai/jobs (type='lead_qualifier') and reports
    progress/result/error through the AiJob row instead.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from src.config.settings import settings
    from src.modules.deals.application.service import DealsService
    from src.shared.dependencies.ai import get_ai_facade

    async def _run() -> dict:
        engine = create_async_engine(str(settings.database_url))
        factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
        )
        try:
            async with factory() as session:
                jobs_repo = AiJobsRepository(db=session)
                job = await jobs_repo.get_by_id(_uuid.UUID(job_id))
                if job is None:
                    log.error("qualify_deal_job.job_missing", job_id=job_id)
                    return {}
                if job.status not in (AiJobStatus.QUEUED.value, AiJobStatus.RUNNING.value):
                    log.warning(
                        "qualify_deal_job.skip_terminal_job", job_id=job_id, status=job.status
                    )
                    return job.result or {}

                if job.status == AiJobStatus.QUEUED.value:
                    await jobs_repo.mark_running(job)
                    await session.commit()

                try:
                    result = await DealsService(
                        db=session, ai_facade=get_ai_facade()
                    ).qualify_deal(
                        user_id=job.owner_user_id,
                        deal_id=job.entity_id,
                    )
                except Exception as exc:
                    if await _was_cancelled(jobs_repo, job):
                        log.info("qualify_deal_job.skip_cancelled", job_id=job_id)
                        return job.result or {}
                    if not _should_retry(
                        exc, current_retries=self.request.retries, max_retries=self.max_retries
                    ):
                        await jobs_repo.mark_failed(job, to_job_error(exc))
                        await session.commit()
                    raise

                if await _was_cancelled(jobs_repo, job):
                    log.info("qualify_deal_job.skip_cancelled", job_id=job_id)
                    return job.result or {}

                result = result or {}
                await jobs_repo.mark_succeeded(job, result)
                await session.commit()
                return result
        finally:
            await engine.dispose()

    try:
        log.info("qualify_deal_job.start", job_id=job_id)
        result = asyncio.run(_run())
        log.info("qualify_deal_job.done", job_id=job_id)
        return result
    except Exception as exc:
        if _should_retry(exc, current_retries=self.request.retries, max_retries=self.max_retries):
            log.warning("qualify_deal_job.retrying", job_id=job_id, error=str(exc))
            raise self.retry(exc=exc) from exc
        log.error("qualify_deal_job.failed", job_id=job_id, error=str(exc))
        return {}


@celery_app.task(
    name="src.workers.ai_jobs.tasks.generate_proposal_async",
    bind=True,
    max_retries=3,
    default_retry_delay=15,
)
def generate_proposal_async(self, job_id: str) -> dict:  # type: ignore[misc]
    """Run AI proposal generation for the deal referenced by an AiJob row.

    The AiJob (entity_type='deal', entity_id=<deal_id>) drives this task —
    all identifying info is read from the row rather than passed as args, so
    the job's persisted status/result/error stay the single source of truth.
    Retries up to 3 times (15 s apart) only for transient (retryable) failures.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from src.config.settings import settings
    from src.modules.proposals.application.service import ProposalsService
    from src.shared.dependencies.ai import get_ai_facade

    async def _run() -> dict:
        engine = create_async_engine(str(settings.database_url))
        factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
        )
        try:
            async with factory() as session:
                jobs_repo = AiJobsRepository(db=session)
                job = await jobs_repo.get_by_id(_uuid.UUID(job_id))
                if job is None:
                    log.error("generate_proposal.job_missing", job_id=job_id)
                    return {}
                if job.status not in (AiJobStatus.QUEUED.value, AiJobStatus.RUNNING.value):
                    log.warning(
                        "generate_proposal.skip_terminal_job", job_id=job_id, status=job.status
                    )
                    return job.result or {}

                if job.status == AiJobStatus.QUEUED.value:
                    await jobs_repo.mark_running(job)
                    await session.commit()

                try:
                    proposal = await ProposalsService(db=session).generate_from_deal(
                        user_id=job.owner_user_id,
                        deal_id=job.entity_id,
                        ai_facade=get_ai_facade(),
                    )
                except Exception as exc:
                    if await _was_cancelled(jobs_repo, job):
                        log.info("generate_proposal.skip_cancelled", job_id=job_id)
                        return job.result or {}
                    if not _should_retry(
                        exc, current_retries=self.request.retries, max_retries=self.max_retries
                    ):
                        await jobs_repo.mark_failed(job, to_job_error(exc))
                        await session.commit()
                    raise

                if await _was_cancelled(jobs_repo, job):
                    log.info("generate_proposal.skip_cancelled", job_id=job_id)
                    return job.result or {}

                result: dict[str, object] = {"proposal_id": str(proposal.id)}
                await jobs_repo.mark_succeeded(job, result)
                await session.commit()
                return result
        finally:
            await engine.dispose()

    try:
        log.info("generate_proposal.start", job_id=job_id)
        result = asyncio.run(_run())
        log.info("generate_proposal.done", job_id=job_id)
        return result
    except Exception as exc:
        if _should_retry(exc, current_retries=self.request.retries, max_retries=self.max_retries):
            log.warning("generate_proposal.retrying", job_id=job_id, error=str(exc))
            raise self.retry(exc=exc) from exc
        log.error("generate_proposal.failed", job_id=job_id, error=str(exc))
        return {}


@celery_app.task(
    name="src.workers.ai_jobs.tasks.generate_contract_async",
    bind=True,
    max_retries=3,
    default_retry_delay=15,
)
def generate_contract_async(self, job_id: str) -> dict:  # type: ignore[misc]
    """Run AI contract generation for the contract referenced by an AiJob row.

    The AiJob (entity_type='contract', entity_id=<contract_id>) drives this
    task. Unlike proposals, contracts must already exist (created from an
    accepted proposal) before AI content can be generated for them — this
    task fills in a draft contract's content, it does not create the contract.
    Retries up to 3 times (15 s apart) only for transient (retryable) failures.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from src.config.settings import settings
    from src.modules.contracts.application.service import ContractsService
    from src.shared.dependencies.ai import get_ai_facade

    async def _run() -> dict:
        engine = create_async_engine(str(settings.database_url))
        factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
        )
        try:
            async with factory() as session:
                jobs_repo = AiJobsRepository(db=session)
                job = await jobs_repo.get_by_id(_uuid.UUID(job_id))
                if job is None:
                    log.error("generate_contract.job_missing", job_id=job_id)
                    return {}
                if job.status not in (AiJobStatus.QUEUED.value, AiJobStatus.RUNNING.value):
                    log.warning(
                        "generate_contract.skip_terminal_job", job_id=job_id, status=job.status
                    )
                    return job.result or {}

                if job.status == AiJobStatus.QUEUED.value:
                    await jobs_repo.mark_running(job)
                    await session.commit()

                try:
                    contract = await ContractsService(db=session).generate_content(
                        user_id=job.owner_user_id,
                        contract_id=job.entity_id,
                        ai_facade=get_ai_facade(),
                    )
                except Exception as exc:
                    if await _was_cancelled(jobs_repo, job):
                        log.info("generate_contract.skip_cancelled", job_id=job_id)
                        return job.result or {}
                    if not _should_retry(
                        exc, current_retries=self.request.retries, max_retries=self.max_retries
                    ):
                        await jobs_repo.mark_failed(job, to_job_error(exc))
                        await session.commit()
                    raise

                if await _was_cancelled(jobs_repo, job):
                    log.info("generate_contract.skip_cancelled", job_id=job_id)
                    return job.result or {}

                result: dict[str, object] = {"contract_id": str(contract.id)}
                await jobs_repo.mark_succeeded(job, result)
                await session.commit()
                return result
        finally:
            await engine.dispose()

    try:
        log.info("generate_contract.start", job_id=job_id)
        result = asyncio.run(_run())
        log.info("generate_contract.done", job_id=job_id)
        return result
    except Exception as exc:
        if _should_retry(exc, current_retries=self.request.retries, max_retries=self.max_retries):
            log.warning("generate_contract.retrying", job_id=job_id, error=str(exc))
            raise self.retry(exc=exc) from exc
        log.error("generate_contract.failed", job_id=job_id, error=str(exc))
        return {}
