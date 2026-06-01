"""Celery tasks for PDF rendering and storage."""

from src.infrastructure.celery.app import celery_app


@celery_app.task(name="src.workers.pdf_jobs.tasks.render_proposal_pdf", bind=True)
def render_proposal_pdf(self, proposal_id: str) -> dict:  # type: ignore[misc]
    # TODO: render proposal to PDF and upload to object storage
    raise NotImplementedError


@celery_app.task(name="src.workers.pdf_jobs.tasks.render_contract_pdf", bind=True)
def render_contract_pdf(self, contract_id: str) -> dict:  # type: ignore[misc]
    raise NotImplementedError


@celery_app.task(name="src.workers.pdf_jobs.tasks.render_invoice_pdf", bind=True)
def render_invoice_pdf(self, invoice_id: str) -> dict:  # type: ignore[misc]
    raise NotImplementedError
