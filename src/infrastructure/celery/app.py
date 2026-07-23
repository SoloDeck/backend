from celery import Celery

from src.config.settings import settings

celery_app = Celery(
    "solodesk",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "src.workers.ai_jobs.tasks",
        "src.workers.pdf_jobs.tasks",
        "src.workers.reminder_jobs.tasks",
        "src.workers.subscription_jobs.tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Ho_Chi_Minh",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=300,  # 5 min soft limit
    task_time_limit=360,  # 6 min hard limit
    result_expires=3600,
    beat_schedule={
        "mark-overdue-invoices": {
            "task": "src.workers.reminder_jobs.tasks.mark_overdue_invoices",
            "schedule": 3600.0,  # every hour
        },
        "send-pending-reminders": {
            "task": "src.workers.reminder_jobs.tasks.send_pending_reminders",
            "schedule": 60.0,  # every minute
        },
        "refresh-analytics-snapshots": {
            "task": "src.workers.reminder_jobs.tasks.refresh_analytics_snapshots",
            "schedule": 86400.0,  # nightly
        },
        "expire-lapsed-subscriptions": {
            "task": "src.workers.subscription_jobs.tasks.expire_lapsed_subscriptions",
            "schedule": 3600.0,  # every hour
        },
    },
)
