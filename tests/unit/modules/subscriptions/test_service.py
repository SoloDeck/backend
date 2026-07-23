import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from src.integrations.momo.client import MockMomoClient
from src.modules.subscriptions.application.service import SubscriptionsService
from src.modules.subscriptions.domain.entities.subscription_payment import PaymentProvider
from src.modules.subscriptions.domain.exceptions.exceptions import (
    InvalidPaymentSignatureError,
    PlanNotPurchasableError,
    SubscriptionNotCancellableError,
)
from src.shared.exceptions.domain import InvalidStateTransitionError, NotFoundError


@dataclass
class SubscriptionStub:
    id: uuid.UUID
    user_id: uuid.UUID
    plan_id: uuid.UUID
    status: str = "active"
    current_period_start: datetime = datetime(2026, 1, 1, tzinfo=UTC)
    current_period_end: datetime = datetime(2026, 2, 1, tzinfo=UTC)
    cancel_at_period_end: bool = False
    cancelled_at: datetime | None = None


@dataclass
class PlanStub:
    id: uuid.UUID
    name: str = "Pro"
    slug: str = "pro"
    price_monthly: Decimal = Decimal("199000")
    currency: str = "VND"
    is_active: bool = True


@dataclass
class PaymentStub:
    id: uuid.UUID
    user_id: uuid.UUID
    subscription_id: uuid.UUID
    plan_id: uuid.UUID
    provider: str = "momo"
    status: str = "pending"
    amount: Decimal = Decimal("199000")
    currency: str = "VND"
    pay_url: str | None = None
    deeplink: str | None = None
    qr_code_url: str | None = None
    provider_reference: str | None = None
    failure_reason: str | None = None
    raw_create_response: dict | None = None
    raw_callback_payload: dict | None = None
    expires_at: datetime = field(
        default_factory=lambda: datetime.now(UTC) + timedelta(minutes=15)
    )
    paid_at: datetime | None = None
    created_at: datetime = datetime(2026, 1, 1, tzinfo=UTC)
    updated_at: datetime = datetime(2026, 1, 1, tzinfo=UTC)


def _repo(**overrides) -> AsyncMock:
    repo = AsyncMock()
    repo.save.side_effect = lambda obj: obj
    for key, value in overrides.items():
        getattr(repo, key).return_value = value
    return repo


# ---------------------------------------------------------------------------
# initiate_checkout
# ---------------------------------------------------------------------------


async def test_initiate_checkout_creates_pending_payment() -> None:
    user_id, sub_id, plan_id, payment_id = (uuid.uuid4() for _ in range(4))
    plan = PlanStub(id=plan_id)
    repo = _repo(
        get_subscription=SubscriptionStub(id=sub_id, user_id=user_id, plan_id=uuid.uuid4()),
        get_plan=plan,
        create_payment=PaymentStub(id=payment_id, user_id=user_id, subscription_id=sub_id, plan_id=plan_id),
    )
    service = SubscriptionsService(db=AsyncMock(), repo=repo, momo_client=MockMomoClient())

    result = await service.initiate_checkout(user_id, plan_id, PaymentProvider.MOMO)

    assert result.pay_url is not None
    assert result.qr_code_url is not None
    create_kwargs = repo.create_payment.await_args.kwargs
    assert create_kwargs["status"] == "pending"
    assert create_kwargs["provider"] == "momo"
    assert create_kwargs["amount"] == plan.price_monthly


async def test_initiate_checkout_rejects_free_plan() -> None:
    user_id, plan_id = uuid.uuid4(), uuid.uuid4()
    repo = _repo(
        get_subscription=SubscriptionStub(id=uuid.uuid4(), user_id=user_id, plan_id=uuid.uuid4()),
        get_plan=PlanStub(id=plan_id, price_monthly=Decimal("0")),
    )
    service = SubscriptionsService(db=AsyncMock(), repo=repo, momo_client=MockMomoClient())

    with pytest.raises(PlanNotPurchasableError):
        await service.initiate_checkout(user_id, plan_id, PaymentProvider.MOMO)


async def test_initiate_checkout_missing_subscription_raises_not_found() -> None:
    repo = _repo(get_subscription=None)
    service = SubscriptionsService(db=AsyncMock(), repo=repo, momo_client=MockMomoClient())

    with pytest.raises(NotFoundError):
        await service.initiate_checkout(uuid.uuid4(), uuid.uuid4(), PaymentProvider.MOMO)


async def test_initiate_checkout_forwards_return_url_to_gateway() -> None:
    user_id, sub_id, plan_id, payment_id = (uuid.uuid4() for _ in range(4))
    plan = PlanStub(id=plan_id)
    payment = PaymentStub(
        id=payment_id, user_id=user_id, subscription_id=sub_id, plan_id=plan_id
    )
    repo = _repo(
        get_subscription=SubscriptionStub(id=sub_id, user_id=user_id, plan_id=uuid.uuid4()),
        get_plan=plan,
        create_payment=payment,
    )
    service = SubscriptionsService(db=AsyncMock(), repo=repo, momo_client=MockMomoClient())
    return_url = "https://app.solodesk.space/billing/result"

    result = await service.initiate_checkout(
        user_id, plan_id, PaymentProvider.MOMO, return_url=return_url
    )

    assert result.raw_create_response["redirectUrl"] == return_url


async def test_initiate_checkout_falls_back_when_no_return_url_given() -> None:
    user_id, sub_id, plan_id, payment_id = (uuid.uuid4() for _ in range(4))
    plan = PlanStub(id=plan_id)
    payment = PaymentStub(
        id=payment_id, user_id=user_id, subscription_id=sub_id, plan_id=plan_id
    )
    repo = _repo(
        get_subscription=SubscriptionStub(id=sub_id, user_id=user_id, plan_id=uuid.uuid4()),
        get_plan=plan,
        create_payment=payment,
    )
    service = SubscriptionsService(db=AsyncMock(), repo=repo, momo_client=MockMomoClient())

    result = await service.initiate_checkout(user_id, plan_id, PaymentProvider.MOMO)

    # MockMomoClient has no configured default redirect_url — falls back to notify_url.
    assert result.raw_create_response["redirectUrl"]


# ---------------------------------------------------------------------------
# handle_payment_callback
# ---------------------------------------------------------------------------


async def test_callback_success_upgrades_subscription_and_records_billing_event() -> None:
    momo = MockMomoClient()
    user_id, sub_id, plan_id, payment_id = (uuid.uuid4() for _ in range(4))
    payload = momo.sign_ipn(order_id=str(payment_id), amount=199000, trans_id=555)

    payment = PaymentStub(
        id=payment_id, user_id=user_id, subscription_id=sub_id, plan_id=plan_id, status="pending"
    )
    subscription = SubscriptionStub(id=sub_id, user_id=user_id, plan_id=uuid.uuid4())
    plan = PlanStub(id=plan_id, slug="pro")
    repo = _repo(
        get_payment_by_id_for_update=payment, get_plan=plan, get_subscription=subscription
    )
    repo.create_billing_event = AsyncMock()
    service = SubscriptionsService(db=AsyncMock(), repo=repo, momo_client=momo)

    ack = await service.handle_payment_callback(PaymentProvider.MOMO, payload)

    assert ack["resultCode"] == 0
    assert payment.status == "succeeded"
    assert payment.provider_reference == "555"
    assert subscription.plan_id == plan_id
    assert subscription.status == "active"
    repo.create_billing_event.assert_awaited_once()
    assert repo.create_billing_event.await_args.kwargs["event_type"] == "payment_succeeded"


async def test_callback_failure_marks_payment_failed_without_touching_subscription() -> None:
    momo = MockMomoClient()
    user_id, sub_id, plan_id, payment_id = (uuid.uuid4() for _ in range(4))
    payload = momo.sign_ipn(
        order_id=str(payment_id), amount=199000, result_code=1, message="User cancelled"
    )

    payment = PaymentStub(
        id=payment_id, user_id=user_id, subscription_id=sub_id, plan_id=plan_id, status="pending"
    )
    repo = _repo(get_payment_by_id_for_update=payment)
    repo.create_billing_event = AsyncMock()
    service = SubscriptionsService(db=AsyncMock(), repo=repo, momo_client=momo)

    await service.handle_payment_callback(PaymentProvider.MOMO, payload)

    assert payment.status == "failed"
    assert payment.failure_reason == "User cancelled"
    repo.get_subscription.assert_not_awaited()
    assert repo.create_billing_event.await_args.kwargs["event_type"] == "payment_failed"


async def test_callback_rejects_tampered_signature() -> None:
    momo = MockMomoClient()
    payload = momo.sign_ipn(order_id=str(uuid.uuid4()), amount=199000)
    payload["amount"] = payload["amount"] + 1  # tamper after signing

    repo = _repo()
    service = SubscriptionsService(db=AsyncMock(), repo=repo, momo_client=momo)

    with pytest.raises(InvalidPaymentSignatureError):
        await service.handle_payment_callback(PaymentProvider.MOMO, payload)
    repo.get_payment_by_id_for_update.assert_not_awaited()


async def test_callback_is_idempotent_for_already_completed_payment() -> None:
    momo = MockMomoClient()
    payment_id = uuid.uuid4()
    payload = momo.sign_ipn(order_id=str(payment_id), amount=199000)

    payment = PaymentStub(
        id=payment_id, user_id=uuid.uuid4(), subscription_id=uuid.uuid4(), plan_id=uuid.uuid4(),
        status="succeeded",
    )
    repo = _repo(get_payment_by_id_for_update=payment)
    repo.create_billing_event = AsyncMock()
    service = SubscriptionsService(db=AsyncMock(), repo=repo, momo_client=momo)

    ack = await service.handle_payment_callback(PaymentProvider.MOMO, payload)

    assert ack["resultCode"] == 0
    repo.create_billing_event.assert_not_awaited()
    repo.get_subscription.assert_not_awaited()


async def test_callback_unknown_order_raises_not_found() -> None:
    momo = MockMomoClient()
    payload = momo.sign_ipn(order_id=str(uuid.uuid4()), amount=199000)
    repo = _repo(get_payment_by_id_for_update=None)
    service = SubscriptionsService(db=AsyncMock(), repo=repo, momo_client=momo)

    with pytest.raises(NotFoundError):
        await service.handle_payment_callback(PaymentProvider.MOMO, payload)


async def test_callback_on_expired_checkout_does_not_activate_subscription() -> None:
    momo = MockMomoClient()
    payment_id = uuid.uuid4()
    payload = momo.sign_ipn(order_id=str(payment_id), amount=199000)

    payment = PaymentStub(
        id=payment_id,
        user_id=uuid.uuid4(),
        subscription_id=uuid.uuid4(),
        plan_id=uuid.uuid4(),
        status="pending",
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    repo = _repo(get_payment_by_id_for_update=payment)
    repo.create_billing_event = AsyncMock()
    service = SubscriptionsService(db=AsyncMock(), repo=repo, momo_client=momo)

    ack = await service.handle_payment_callback(PaymentProvider.MOMO, payload)

    assert ack["resultCode"] == 0
    assert payment.status == "expired"
    repo.get_subscription.assert_not_awaited()
    repo.create_billing_event.assert_not_awaited()


# ---------------------------------------------------------------------------
# get_checkout_status
# ---------------------------------------------------------------------------


async def test_get_checkout_status_expires_stale_pending_payment() -> None:
    user_id, payment_id = uuid.uuid4(), uuid.uuid4()
    payment = PaymentStub(
        id=payment_id,
        user_id=user_id,
        subscription_id=uuid.uuid4(),
        plan_id=uuid.uuid4(),
        status="pending",
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    repo = _repo(get_payment_by_id=payment)
    service = SubscriptionsService(db=AsyncMock(), repo=repo, momo_client=MockMomoClient())

    result = await service.get_checkout_status(user_id, payment_id)

    assert result.status == "expired"


async def test_get_checkout_status_leaves_unexpired_pending_payment_alone() -> None:
    user_id, payment_id = uuid.uuid4(), uuid.uuid4()
    payment = PaymentStub(
        id=payment_id, user_id=user_id, subscription_id=uuid.uuid4(), plan_id=uuid.uuid4(),
        status="pending",
    )
    repo = _repo(get_payment_by_id=payment)
    service = SubscriptionsService(db=AsyncMock(), repo=repo, momo_client=MockMomoClient())

    result = await service.get_checkout_status(user_id, payment_id)

    assert result.status == "pending"


# ---------------------------------------------------------------------------
# cancel_checkout
# ---------------------------------------------------------------------------


async def test_cancel_checkout_cancels_pending_payment() -> None:
    user_id, payment_id = uuid.uuid4(), uuid.uuid4()
    payment = PaymentStub(
        id=payment_id, user_id=user_id, subscription_id=uuid.uuid4(), plan_id=uuid.uuid4(),
        status="pending",
    )
    repo = _repo(get_payment_by_id=payment)
    service = SubscriptionsService(db=AsyncMock(), repo=repo, momo_client=MockMomoClient())

    result = await service.cancel_checkout(user_id, payment_id)

    assert result.status == "cancelled"


async def test_cancel_checkout_rejects_already_succeeded_payment() -> None:
    user_id, payment_id = uuid.uuid4(), uuid.uuid4()
    payment = PaymentStub(
        id=payment_id, user_id=user_id, subscription_id=uuid.uuid4(), plan_id=uuid.uuid4(),
        status="succeeded",
    )
    repo = _repo(get_payment_by_id=payment)
    service = SubscriptionsService(db=AsyncMock(), repo=repo, momo_client=MockMomoClient())

    with pytest.raises(InvalidStateTransitionError):
        await service.cancel_checkout(user_id, payment_id)


# ---------------------------------------------------------------------------
# cancel_subscription
# ---------------------------------------------------------------------------


async def test_cancel_subscription_schedules_cancellation_at_period_end() -> None:
    user_id, plan_id = uuid.uuid4(), uuid.uuid4()
    subscription = SubscriptionStub(id=uuid.uuid4(), user_id=user_id, plan_id=plan_id)
    plan = PlanStub(id=plan_id, slug="pro")
    repo = _repo(get_subscription=subscription, get_plan=plan)
    service = SubscriptionsService(db=AsyncMock(), repo=repo, momo_client=MockMomoClient())

    result = await service.cancel_subscription(user_id)

    assert result.cancel_at_period_end is True
    assert result.status == "active"  # access continues until period end
    assert subscription.cancelled_at is not None


async def test_cancel_subscription_rejects_free_plan() -> None:
    user_id, plan_id = uuid.uuid4(), uuid.uuid4()
    subscription = SubscriptionStub(id=uuid.uuid4(), user_id=user_id, plan_id=plan_id)
    plan = PlanStub(id=plan_id, slug="free", price_monthly=Decimal("0"))
    repo = _repo(get_subscription=subscription, get_plan=plan)
    service = SubscriptionsService(db=AsyncMock(), repo=repo, momo_client=MockMomoClient())

    with pytest.raises(SubscriptionNotCancellableError):
        await service.cancel_subscription(user_id)


async def test_cancel_subscription_rejects_already_scheduled() -> None:
    user_id, plan_id = uuid.uuid4(), uuid.uuid4()
    subscription = SubscriptionStub(
        id=uuid.uuid4(), user_id=user_id, plan_id=plan_id, cancel_at_period_end=True
    )
    plan = PlanStub(id=plan_id, slug="pro")
    repo = _repo(get_subscription=subscription, get_plan=plan)
    service = SubscriptionsService(db=AsyncMock(), repo=repo, momo_client=MockMomoClient())

    with pytest.raises(SubscriptionNotCancellableError):
        await service.cancel_subscription(user_id)


async def test_cancel_subscription_missing_subscription_raises_not_found() -> None:
    repo = _repo(get_subscription=None)
    service = SubscriptionsService(db=AsyncMock(), repo=repo, momo_client=MockMomoClient())

    with pytest.raises(NotFoundError):
        await service.cancel_subscription(uuid.uuid4())


# ---------------------------------------------------------------------------
# expire_lapsed_subscriptions
# ---------------------------------------------------------------------------


async def test_expire_lapsed_subscriptions_downgrades_and_records_expired_event() -> None:
    free_plan = PlanStub(id=uuid.uuid4(), slug="free", price_monthly=Decimal("0"))
    sub = SubscriptionStub(
        id=uuid.uuid4(), user_id=uuid.uuid4(), plan_id=uuid.uuid4(), cancel_at_period_end=False
    )
    repo = _repo(get_free_plan=free_plan, list_lapsed_subscriptions=[sub])
    repo.create_billing_event = AsyncMock()
    service = SubscriptionsService(db=AsyncMock(), repo=repo, momo_client=MockMomoClient())

    count = await service.expire_lapsed_subscriptions()

    assert count == 1
    assert sub.plan_id == free_plan.id
    assert sub.status == "active"
    assert sub.cancel_at_period_end is False
    repo.create_billing_event.assert_awaited_once()
    assert repo.create_billing_event.await_args.kwargs["event_type"] == "subscription_expired"


async def test_expire_lapsed_subscriptions_uses_cancelled_event_when_flagged() -> None:
    free_plan = PlanStub(id=uuid.uuid4(), slug="free", price_monthly=Decimal("0"))
    sub = SubscriptionStub(
        id=uuid.uuid4(), user_id=uuid.uuid4(), plan_id=uuid.uuid4(), cancel_at_period_end=True
    )
    repo = _repo(get_free_plan=free_plan, list_lapsed_subscriptions=[sub])
    repo.create_billing_event = AsyncMock()
    service = SubscriptionsService(db=AsyncMock(), repo=repo, momo_client=MockMomoClient())

    await service.expire_lapsed_subscriptions()

    assert repo.create_billing_event.await_args.kwargs["event_type"] == "subscription_cancelled"


async def test_expire_lapsed_subscriptions_noop_when_none_lapsed() -> None:
    free_plan = PlanStub(id=uuid.uuid4(), slug="free", price_monthly=Decimal("0"))
    repo = _repo(get_free_plan=free_plan, list_lapsed_subscriptions=[])
    repo.create_billing_event = AsyncMock()
    service = SubscriptionsService(db=AsyncMock(), repo=repo, momo_client=MockMomoClient())

    count = await service.expire_lapsed_subscriptions()

    assert count == 0
    repo.create_billing_event.assert_not_awaited()


async def test_expire_lapsed_subscriptions_noop_when_no_free_plan_configured() -> None:
    repo = _repo(get_free_plan=None)
    service = SubscriptionsService(db=AsyncMock(), repo=repo, momo_client=MockMomoClient())

    count = await service.expire_lapsed_subscriptions()

    assert count == 0
    repo.list_lapsed_subscriptions.assert_not_awaited()
