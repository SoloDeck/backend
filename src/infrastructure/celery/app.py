from celery import Celery
from celery.schedules import crontab

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
        # Quét quy tắc nhắc tự động, mỗi ngày một lần lúc 1h sáng (giờ VN — xem `timezone`
        # ở trên). Chạy SAU `mark-overdue-invoices` để hoá đơn kịp chuyển sang `overdue`
        # trước khi quy tắc "nhắc quá hạn" đi tìm chúng.  #Huynh
        "generate-rule-reminders": {
            "task": "src.workers.reminder_jobs.tasks.generate_rule_reminders",
            "schedule": crontab(hour=1, minute=0),
        },
        "refresh-analytics-snapshots": {
            "task": "src.workers.reminder_jobs.tasks.refresh_analytics_snapshots",
            "schedule": 86400.0,  # nightly
        },
        "expire-lapsed-subscriptions": {
            "task": "src.workers.subscription_jobs.tasks.expire_lapsed_subscriptions",
            "schedule": 3600.0,  # every hour
        },
        # Cửa sổ thanh toán chỉ 30 phút (xem SubscriptionsService.initiate_checkout), nên
        # quét dày hơn job hạ gói ở trên — 10 phút vẫn đủ thưa để không tốn gì, nhưng
        # không để một đơn SePay bị bỏ dở đứng "pending" hàng giờ trước mắt admin.  #Huynh
        "expire-stale-payment-intents": {
            "task": "src.workers.subscription_jobs.tasks.expire_stale_payment_intents",
            "schedule": 600.0,  # every 10 minutes
        },
        # Cảnh báo EMAIL: sắp hết quota AI (giữa kỳ) + sắp hết kỳ. Mỗi ngày một lần lúc 2h
        # sáng (giờ VN). KHÔNG hạ gói ở đây — việc hạ Free khi hết kỳ do
        # `expire-lapsed-subscriptions` (module subscriptions) lo, tránh hạ 2 lần.
        "run-subscription-maintenance": {
            "task": "src.workers.reminder_jobs.tasks.run_subscription_maintenance",
            "schedule": crontab(hour=2, minute=0),
        },
    },
)
