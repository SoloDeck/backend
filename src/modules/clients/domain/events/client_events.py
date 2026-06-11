import uuid
from dataclasses import dataclass

from src.modules.clients.domain.value_objects.client_status import ClientStatus
from src.shared.domain.base import DomainEvent


@dataclass(frozen=True)
class ClientCreatedEvent(DomainEvent):
    owner_user_id: uuid.UUID
    full_name: str
    email: str | None


@dataclass(frozen=True)
class ClientStatusChangedEvent(DomainEvent):
    old_status: ClientStatus
    new_status: ClientStatus


@dataclass(frozen=True)
class ClientArchivedEvent(DomainEvent):
    owner_user_id: uuid.UUID


@dataclass(frozen=True)
class ClientDeletedEvent(DomainEvent):
    owner_user_id: uuid.UUID
