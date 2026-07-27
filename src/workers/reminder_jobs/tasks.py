"""Celery tasks for reminder delivery and scheduled jobs."""

import structlog

from src.infrastructure.celery.app import celery_app

log = structlog.get_logger()


@celery_app.task(
    name="src.workers.reminder_jobs.tasks.send_reminder",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def send_reminder(self, reminder_id: str) -> dict:  # type: ignore[misc]
    """Gửi MỘT lời nhắc: email cho khách, hoặc thông báo trong ứng dụng cho freelancer.

    Toàn bộ nghiệp vụ nằm ở `ReminderDeliveryService` — task này chỉ lo phần Celery: mở
    session, commit, và quyết định có thử lại hay không. Nhờ vậy endpoint "Gửi ngay" dùng
    lại được đúng đường code này mà không phải chạy qua hàng đợi.  #Huynh
    """
    import asyncio
    import uuid as _uuid

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from src.config.settings import settings
    from src.modules.reminders.application.delivery_service import ReminderDeliveryService

    async def _run() -> tuple[str, str, bool]:
        engine = create_async_engine(str(settings.database_url))
        factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
        )
        try:
            async with factory() as session:
                result = await ReminderDeliveryService(db=session).deliver(_uuid.UUID(reminder_id))
                # Commit KỂ CẢ khi gửi hỏng: lượt thử vừa rồi (retry_count, delivery
                # record, thông báo báo lỗi) là dữ liệu phải giữ, không phải rác cần
                # rollback. Rollback ở đây là mất dấu vết vì sao hỏng.
                await session.commit()
                return result.status, result.detail, result.should_retry
        finally:
            await engine.dispose()

    status, detail, should_retry = asyncio.run(_run())

    if should_retry:
        log.info("send_reminder.retrying", reminder_id=reminder_id, attempt=self.request.retries)
        raise self.retry(exc=RuntimeError(detail))

    return {"reminder_id": reminder_id, "status": status, "detail": detail}


@celery_app.task(name="src.workers.reminder_jobs.tasks.send_pending_reminders")
def send_pending_reminders() -> None:
    """Beat mỗi phút: tìm lời nhắc tới giờ rồi xếp vào hàng đợi.

    Task này TỪNG là `raise NotImplementedError` trong khi beat vẫn gọi nó 60 giây một
    lần — worker log lỗi liên tục, còn lời nhắc thì nằm im ở `pending` vĩnh viễn.  #Huynh
    """
    import asyncio

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from src.config.settings import settings
    from src.modules.reminders.infrastructure.repository import RemindersRepository

    async def _run() -> list[str]:
        engine = create_async_engine(str(settings.database_url))
        factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
        )
        try:
            async with factory() as session:
                due = await RemindersRepository(session).list_due()
                ids = [str(reminder.id) for reminder in due]
                # Nhả khoá hàng TRƯỚC khi xếp việc: giữ khoá trong lúc worker chạy
                # `send_reminder` thì chính nó lại bị khoá đó chặn.
                await session.commit()
                return ids
        finally:
            await engine.dispose()

    reminder_ids = asyncio.run(_run())
    for reminder_id in reminder_ids:
        send_reminder.delay(reminder_id)

    if reminder_ids:
        log.info("send_pending_reminders.queued", count=len(reminder_ids))


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


@celery_app.task(name="src.workers.reminder_jobs.tasks.generate_rule_reminders")
def generate_rule_reminders() -> None:
    """Chạy mỗi ngày: quét cả hệ thống, soạn sẵn lời nhắc theo quy tắc của từng người.

    Trước đây hệ thống chỉ gửi được lời nhắc do người dùng TỰ TẠO TAY — nghĩa là freelancer
    vẫn phải tự nhớ hoá đơn nào sắp tới hạn, khách nào chưa phản hồi báo giá. Phiếu đòi
    "nhắc nhở TỰ ĐỘNG", và đây là phần đó.

    Task này CHỈ TẠO lời nhắc `pending`; việc gửi vẫn do `send_pending_reminders` lo. Chưa
    bật "tự gửi" thì lời nhắc mang cờ `requires_approval` và nằm im chờ người duyệt.  #Huynh
    """
    import asyncio

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from src.config.settings import settings
    from src.modules.reminders.application.auto_scheduler import AutoReminderScheduler

    async def _run() -> dict[str, int]:
        engine = create_async_engine(str(settings.database_url))
        factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
        )
        try:
            async with factory() as session:
                counts = await AutoReminderScheduler(db=session).run()
                await session.commit()
                return counts
        finally:
            await engine.dispose()

    counts = asyncio.run(_run())
    if counts["created"]:
        log.info("generate_rule_reminders.done", **counts)


@celery_app.task(name="src.workers.reminder_jobs.tasks.run_subscription_maintenance")
def run_subscription_maintenance() -> None:
    """Chạy mỗi ngày: gửi email BÁO TRƯỚC khi gói sắp hết kỳ.

    Toàn bộ nghiệp vụ nằm ở `SubscriptionLifecycleService`; task này chỉ lo phần Celery: mở
    session, chạy, commit. CHỈ cảnh báo — việc tự hạ Free khi hết kỳ do
    `subscription_jobs.expire_lapsed_subscriptions` lo. Cảnh báo "sắp hết quota AI" xử lý
    ngay trong `AiUsageService.consume`.  #Huynh
    """
    import asyncio

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from src.config.settings import settings
    from src.modules.subscriptions.application.lifecycle_service import (
        SubscriptionLifecycleService,
    )

    async def _run() -> dict[str, int]:
        engine = create_async_engine(str(settings.database_url))
        factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
        )
        try:
            async with factory() as session:
                counts = await SubscriptionLifecycleService(db=session).run_daily_maintenance()
                await session.commit()
                return counts
        finally:
            await engine.dispose()

    counts = asyncio.run(_run())
    if counts["expiry_warned"]:
        log.info("run_subscription_maintenance.done", **counts)


@celery_app.task(name="src.workers.reminder_jobs.tasks.refresh_analytics_snapshots")
def refresh_analytics_snapshots() -> None:
    """Beat task: nightly refresh of revenue and pipeline snapshots."""
    raise NotImplementedError
