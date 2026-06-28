import uuid
from dataclasses import dataclass

from src.shared.domain.base import DomainEvent


@dataclass(frozen=True)
class SubscriptionCreatedEvent(DomainEvent):
    user_id: uuid.UUID
    plan_slug: str


@dataclass(frozen=True)
class PlanChangedEvent(DomainEvent):
    """Consumed by Auth to re-issue JWT with new subscription tier."""

    user_id: uuid.UUID
    old_plan_slug: str
    new_plan_slug: str


@dataclass(frozen=True)
class SubscriptionSuspendedEvent(DomainEvent):
    user_id: uuid.UUID


@dataclass(frozen=True)
class SubscriptionReactivatedEvent(DomainEvent):
    user_id: uuid.UUID


@dataclass(frozen=True)
class UsageLimitReachedEvent(DomainEvent):
    user_id: uuid.UUID
    feature: str
