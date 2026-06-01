import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from src.shared.domain.base import DomainEvent
from src.modules.subscriptions.domain.entities.subscription import Subscription
from src.modules.subscriptions.domain.entities.subscription_plan import SubscriptionPlan
from src.modules.subscriptions.domain.entities.usage_record import UsageRecord, UsageFeature
from src.modules.subscriptions.domain.value_objects.entitlement import SubscriptionStatus
from src.modules.subscriptions.domain.events.subscription_events import (
    SubscriptionCreatedEvent,
    PlanChangedEvent,
    SubscriptionSuspendedEvent,
    SubscriptionReactivatedEvent,
)


@dataclass
class SubscriptionAggregate:
    subscription: Subscription
    usage_records: list[UsageRecord] = field(default_factory=list)
    _pending_events: list[DomainEvent] = field(
        default_factory=list, init=False, repr=False, compare=False
    )

    @classmethod
    def create_free(
        cls, user_id: uuid.UUID, free_plan: SubscriptionPlan
    ) -> "SubscriptionAggregate":
        now = datetime.now(timezone.utc)
        sub_id = uuid.uuid4()
        subscription = Subscription(
            id=sub_id,
            user_id=user_id,
            plan=free_plan,
            status=SubscriptionStatus.ACTIVE,
            current_period_start=now,
            current_period_end=now + timedelta(days=36500),  # perpetual for free
            cancel_at_period_end=False,
            cancelled_at=None,
            stripe_subscription_id=None,
            stripe_customer_id=None,
            override_by_admin_id=None,
            override_expires_at=None,
            created_at=now,
            updated_at=now,
        )
        agg = cls(subscription=subscription)
        agg._pending_events.append(
            SubscriptionCreatedEvent(
                event_id=uuid.uuid4(),
                aggregate_id=sub_id,
                occurred_at=now,
                user_id=user_id,
                plan_slug=free_plan.slug,
            )
        )
        return agg

    def change_plan(self, new_plan: SubscriptionPlan) -> None:
        old_slug = self.subscription.plan.slug
        self.subscription.change_plan(new_plan)
        self._pending_events.append(
            PlanChangedEvent(
                event_id=uuid.uuid4(),
                aggregate_id=self.subscription.id,
                occurred_at=self.subscription.updated_at,
                user_id=self.subscription.user_id,
                old_plan_slug=old_slug,
                new_plan_slug=new_plan.slug,
            )
        )

    def suspend(self) -> None:
        self.subscription.suspend()
        self._pending_events.append(
            SubscriptionSuspendedEvent(
                event_id=uuid.uuid4(),
                aggregate_id=self.subscription.id,
                occurred_at=self.subscription.updated_at,
                user_id=self.subscription.user_id,
            )
        )

    def reactivate(self) -> None:
        self.subscription.reactivate()
        self._pending_events.append(
            SubscriptionReactivatedEvent(
                event_id=uuid.uuid4(),
                aggregate_id=self.subscription.id,
                occurred_at=self.subscription.updated_at,
                user_id=self.subscription.user_id,
            )
        )

    def check_and_record_usage(
        self,
        feature: UsageFeature,
        tokens_used: int | None = None,
        cost_usd: float | None = None,
    ) -> UsageRecord:
        self.subscription.check_entitlement(feature.value.replace("ai_", "can_use_ai").split("_")[0])
        now = datetime.now(timezone.utc)
        record = UsageRecord(
            id=uuid.uuid4(),
            user_id=self.subscription.user_id,
            subscription_id=self.subscription.id,
            feature=feature,
            used_at=now,
            period_start=self.subscription.current_period_start,
            period_end=self.subscription.current_period_end,
            tokens_used=tokens_used,
            cost_usd=cost_usd,
        )
        self.usage_records.append(record)
        return record

    def pull_events(self) -> list[DomainEvent]:
        events = list(self._pending_events)
        self._pending_events.clear()
        return events
