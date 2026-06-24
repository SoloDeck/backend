"""Celery tasks for long-running AI generation jobs."""

import asyncio
import uuid as _uuid

import structlog

from src.infrastructure.celery.app import celery_app

log = structlog.get_logger()


@celery_app.task(name="src.workers.ai_jobs.tasks.qualify_lead_async", bind=True)
def qualify_lead_async(self, deal_id: str, user_id: str) -> dict:  # type: ignore[misc]
    """Async lead qualification — used when qualification is triggered non-interactively."""
    # TODO: implement
    raise NotImplementedError


@celery_app.task(
    name="src.workers.ai_jobs.tasks.qualify_intake_async",
    bind=True,
    max_retries=3,
    default_retry_delay=15,
)
def qualify_intake_async(self, user_id: str, intake_id: str) -> dict:  # type: ignore[misc]
    """Run AI lead qualification for a DealIntake record.

    Dispatched automatically after a public intake submission so the freelancer
    sees a hot/warm/cold score in their pipeline without manual action.
    Retries up to 3 times (15 s apart) on transient failures.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from src.ai.contract_generator.chain import ContractGenerator
    from src.ai.facade import AIFacade
    from src.ai.followup_generator.chain import FollowUpGenerator
    from src.ai.lead_qualifier.chain import LeadQualifier
    from src.ai.proposal_generator.chain import ProposalGenerator
    from src.config.settings import settings
    from src.modules.deals.application.service import DealsService

    async def _run() -> dict:
        engine = create_async_engine(str(settings.database_url))
        factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
        )
        ai_facade = AIFacade(
            lead_qualifier=LeadQualifier(),
            proposal_generator=ProposalGenerator(),
            contract_generator=ContractGenerator(),
            followup_generator=FollowUpGenerator(),
        )
        try:
            async with factory() as session:
                service = DealsService(db=session, ai_facade=ai_facade)
                result = await service.qualify_deal_intake(
                    user_id=_uuid.UUID(user_id),
                    intake_id=_uuid.UUID(intake_id),
                )
                await session.commit()
                return result or {}
        finally:
            await engine.dispose()

    try:
        log.info("qualify_intake.start", user_id=user_id, intake_id=intake_id)
        result = asyncio.run(_run())
        log.info("qualify_intake.done", user_id=user_id, intake_id=intake_id)
        return result
    except Exception as exc:
        log.error("qualify_intake.failed", user_id=user_id, intake_id=intake_id, error=str(exc))
        raise self.retry(exc=exc)


@celery_app.task(name="src.workers.ai_jobs.tasks.generate_proposal_async", bind=True)
def generate_proposal_async(self, proposal_id: str, user_id: str) -> dict:  # type: ignore[misc]
    """Async proposal generation."""
    raise NotImplementedError


@celery_app.task(name="src.workers.ai_jobs.tasks.generate_contract_async", bind=True)
def generate_contract_async(self, contract_id: str, user_id: str) -> dict:  # type: ignore[misc]
    """Async contract generation."""
    raise NotImplementedError
