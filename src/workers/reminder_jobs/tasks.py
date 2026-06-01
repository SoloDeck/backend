"""Celery tasks for reminder delivery and scheduled jobs."""

from src.infrastructure.celery.app import celery_app


@celery_app.task(name="src.workers.reminder_jobs.tasks.send_reminder", bind=True)
def send_reminder(self, reminder_id: str) -> dict:  # type: ignore[misc]
    # TODO: fetch reminder, deliver via configured channel, update status
    raise NotImplementedError


@celery_app.task(name="src.workers.reminder_jobs.tasks.send_pending_reminders")
def send_pending_reminders() -> None:
    """Beat task: scan pending reminders due for execution and enqueue them."""
    # TODO: query reminders WHERE status='pending' AND scheduled_at <= NOW()
    raise NotImplementedError


@celery_app.task(name="src.workers.reminder_jobs.tasks.mark_overdue_invoices")
def mark_overdue_invoices() -> None:
    """Beat task: mark invoices past due_date as overdue."""
    # TODO: UPDATE invoices SET status='overdue' WHERE due_date < NOW() AND status IN ('sent','partially_paid')
    raise NotImplementedError


@celery_app.task(name="src.workers.reminder_jobs.tasks.refresh_analytics_snapshots")
def refresh_analytics_snapshots() -> None:
    """Beat task: nightly refresh of revenue and pipeline snapshots."""
    raise NotImplementedError
