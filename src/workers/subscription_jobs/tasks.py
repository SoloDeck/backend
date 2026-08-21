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


@celery_app.task(name="src.workers.subscription_jobs.tasks.expire_stale_payment_intents")
def expire_stale_payment_intents() -> int:
    """Beat task: flip `pending` checkout intents past `expires_at` to `expired`.

    `SubscriptionsService._expire_if_overdue` only fires when someone re-reads the
    exact same intent (a poll, an F5) — an abandoned SePay transfer (no redirect to
    bring the user back) or a ZaloPay/MoMo checkout the user never revisits gets no
    such read, and the row sits `pending` forever with nothing to sweep it. Runs for
    every provider; MoMo/ZaloPay also get an earlier, provider-specific chance to
    settle via their return-URL/reconcile paths, so this is the backstop, not the
    primary path, for those two.
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
                count = await SubscriptionsService(db=session).expire_stale_payments()
                await session.commit()
                return count
        finally:
            await engine.dispose()

    log.info("subscriptions.expire_stale_payments.start")
    count = asyncio.run(_run())
    log.info("subscriptions.expire_stale_payments.done", expired_count=count)
    return count
