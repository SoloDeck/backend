from dataclasses import dataclass

from src.modules.users.domain.value_objects.user_status import UserRole
from src.shared.domain.base import DomainEvent


@dataclass(frozen=True)
class UserCreatedEvent(DomainEvent):
    """Consumed by Subscriptions to create a Free plan subscription."""
    email: str
    role: UserRole


@dataclass(frozen=True)
class UserSuspendedEvent(DomainEvent):
    """Consumed by Auth to invalidate active tokens."""
    email: str


@dataclass(frozen=True)
class UserReactivatedEvent(DomainEvent):
    email: str


@dataclass(frozen=True)
class UserDeletedEvent(DomainEvent):
    email: str
