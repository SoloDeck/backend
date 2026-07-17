"""Celery tasks for reminder delivery and scheduled jobs."""

import structlog

from src.infrastructure.celery.app import celery_app

log = structlog.get_logger()


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
    """Chạy mỗi giờ: đánh dấu hoá đơn quá hạn và báo cho freelancer.

    Trước đây hàm này là `raise NotImplementedError` — nghĩa là trạng thái `overdue` KHÔNG
    BAO GIỜ xảy ra. Hoá đơn quá hạn ba tháng vẫn nằm im ở "đã gửi", báo cáo doanh thu vẫn
    tính nó là bình thường, và freelancer không hề biết mình đang bị nợ. Enum có sẵn giá
    trị `overdue` từ đầu, chỉ là chưa ai viết phần điền vào.

    Chỉ chuyển từ `sent` / `partially_paid`. KHÔNG đụng vào `draft` (chưa gửi cho khách thì
    lấy gì mà quá hạn), `paid`, hay `void`.  #Huynh
    """
    import asyncio
    from datetime import UTC, date, datetime

    from sqlalchemy import select, update
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from src.config.settings import settings
    from src.infrastructure.database.models import ClientModel, InvoiceModel
    from src.modules.notifications.application.service import NotificationService

    async def _run() -> int:
        engine = create_async_engine(str(settings.database_url))
        factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
        )
        today = date.today()
        try:
            async with factory() as session:
                # Lấy danh sách TRƯỚC khi cập nhật: sau khi UPDATE thì không còn phân biệt
                # được hoá đơn nào vừa mới quá hạn với hoá đơn đã quá hạn từ tuần trước —
                # mà chỉ hoá đơn VỪA quá hạn mới đáng bắn thông báo.  #Huynh
                rows = (
                    await session.execute(
                        select(InvoiceModel, ClientModel.name)
                        .join(ClientModel, ClientModel.id == InvoiceModel.client_id)
                        .where(
                            InvoiceModel.due_date < today,
                            InvoiceModel.status.in_(("sent", "partially_paid")),
                        )
                    )
                ).all()

                if not rows:
                    return 0

                await session.execute(
                    update(InvoiceModel)
                    .where(InvoiceModel.id.in_([inv.id for inv, _ in rows]))
                    .values(status="overdue", updated_at=datetime.now(UTC))
                )

                notifications = NotificationService(db=session)
                for invoice, client_name in rows:
                    await notifications.notify_invoice_overdue(
                        owner_user_id=invoice.owner_user_id,
                        invoice_id=invoice.id,
                        invoice_number=invoice.invoice_number,
                        client_name=client_name,
                        days_overdue=(today - invoice.due_date).days,
                    )

                await session.commit()
                return len(rows)
        finally:
            await engine.dispose()

    count = asyncio.run(_run())
    if count:
        log.info("mark_overdue_invoices.done", marked=count)


@celery_app.task(name="src.workers.reminder_jobs.tasks.refresh_analytics_snapshots")
def refresh_analytics_snapshots() -> None:
    """Beat task: nightly refresh of revenue and pipeline snapshots."""
    raise NotImplementedError
