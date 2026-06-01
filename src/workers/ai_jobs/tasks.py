"""Celery tasks for long-running AI generation jobs."""

from src.infrastructure.celery.app import celery_app


@celery_app.task(name="src.workers.ai_jobs.tasks.qualify_lead_async", bind=True)
def qualify_lead_async(self, deal_id: str, user_id: str) -> dict:  # type: ignore[misc]
    """Async lead qualification — used when qualification is triggered non-interactively."""
    # TODO: implement
    raise NotImplementedError


@celery_app.task(name="src.workers.ai_jobs.tasks.generate_proposal_async", bind=True)
def generate_proposal_async(self, proposal_id: str, user_id: str) -> dict:  # type: ignore[misc]
    """Async proposal generation."""
    raise NotImplementedError


@celery_app.task(name="src.workers.ai_jobs.tasks.generate_contract_async", bind=True)
def generate_contract_async(self, contract_id: str, user_id: str) -> dict:  # type: ignore[misc]
    """Async contract generation."""
    raise NotImplementedError
