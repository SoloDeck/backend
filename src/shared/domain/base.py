"""Base primitives for Domain-Driven Design.

Import from here in all domain modules — never re-implement these.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class DomainEvent:
    """Immutable record of something that happened within an aggregate."""

    event_id: uuid.UUID
    aggregate_id: uuid.UUID
    occurred_at: datetime

    @classmethod
    def new(cls, aggregate_id: uuid.UUID, **kwargs: object) -> "DomainEvent":
        return cls(
            event_id=uuid.uuid4(),
            aggregate_id=aggregate_id,
            occurred_at=datetime.now(UTC),
            **kwargs,  # type: ignore[arg-type]
        )


@dataclass
class AggregateRoot:
    """Mixin that gives aggregate roots an internal event buffer."""

    _pending_events: list[DomainEvent] = field(
        default_factory=list, init=False, repr=False, compare=False
    )

    def _raise(self, event: DomainEvent) -> None:
        self._pending_events.append(event)

    def pull_events(self) -> list[DomainEvent]:
        """Return all uncommitted events and flush the buffer."""
        events = list(self._pending_events)
        self._pending_events.clear()
        return events
