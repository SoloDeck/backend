"""Celery tasks for subscription lifecycle housekeeping."""

import asyncio

import structlog

from src.infrastructure.celery.app import celery_app

log = structlog.get_logger()


@celery_app.task(name="src.workers.subscription_jobs.tasks.expire_lapsed_subscriptions")
def expire_lapsed_subscriptions() -> int:
    """Beat task: downgrade subscriptions whose billing period has ended back
    to the free plan. MoMo checkout has no recurring auto-charge, so this is
    the only thing that actually enforces `current_period_end` — without it,
    a subscription (cancelled or not) stays on its paid plan forever once the
    period it was paid for ends.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from src.config.settings import settings
    from src.modules.subscriptions.application.service import SubscriptionsService

    async def _run() -> int:
        engine = create_async_engine(str(settings.database_url))
        factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
        )
        try:
            async with factory() as session:
                count = await SubscriptionsService(db=session).expire_lapsed_subscriptions()
                await session.commit()
                return count
        finally:
            await engine.dispose()

    log.info("subscriptions.expire_lapsed.start")
    count = asyncio.run(_run())
    log.info("subscriptions.expire_lapsed.done", expired_count=count)
    return count
