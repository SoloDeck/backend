import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from src.modules.users.domain.entities.user import User
from src.modules.users.domain.events.user_events import (
    UserCreatedEvent,
    UserDeletedEvent,
    UserReactivatedEvent,
    UserSuspendedEvent,
)
from src.modules.users.domain.value_objects.preferences import Preferences
from src.modules.users.domain.value_objects.professional_profile import ProfessionalProfile
from src.modules.users.domain.value_objects.user_status import UserRole, UserStatus
from src.shared.domain.base import DomainEvent


@dataclass
class UserAggregate:
    user: User
    _pending_events: list[DomainEvent] = field(
        default_factory=list, init=False, repr=False, compare=False
    )

    @classmethod
    def register(
        cls,
        email: str,
        full_name: str,
        hashed_password: str | None = None,
        role: UserRole = UserRole.FREELANCER,
    ) -> "UserAggregate":
        now = datetime.now(UTC)
        user_id = uuid.uuid4()
        user = User(
            id=user_id,
            email=email.lower().strip(),
            full_name=full_name.strip(),
            role=role,
            status=UserStatus.ACTIVE,
            hashed_password=hashed_password,
            avatar_url=None,
            bio=None,
            phone=None,
            professional_profile=ProfessionalProfile.empty(),
            preferences=Preferences.default_vietnamese(),
            created_at=now,
            updated_at=now,
            deleted_at=None,
        )
        agg = cls(user=user)
        agg._pending_events.append(
            UserCreatedEvent(
                event_id=uuid.uuid4(),
                aggregate_id=user_id,
                occurred_at=now,
                email=email,
                role=role,
            )
        )
        return agg

    def suspend(self) -> None:
        self.user.suspend()
        self._pending_events.append(
            UserSuspendedEvent(
                event_id=uuid.uuid4(),
                aggregate_id=self.user.id,
                occurred_at=self.user.updated_at,
                email=self.user.email,
            )
        )

    def reactivate(self) -> None:
        self.user.reactivate()
        self._pending_events.append(
            UserReactivatedEvent(
                event_id=uuid.uuid4(),
                aggregate_id=self.user.id,
                occurred_at=self.user.updated_at,
                email=self.user.email,
            )
        )

    def delete(self) -> None:
        self.user.soft_delete()
        self._pending_events.append(
            UserDeletedEvent(
                event_id=uuid.uuid4(),
                aggregate_id=self.user.id,
                occurred_at=self.user.updated_at,
                email=self.user.email,
            )
        )

    def pull_events(self) -> list[DomainEvent]:
        events = list(self._pending_events)
        self._pending_events.clear()
        return events
