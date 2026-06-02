import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.shared.domain.base import DomainEvent
from src.modules.clients.domain.entities.client import Client
from src.modules.clients.domain.entities.client_contact import ClientContact
from src.modules.clients.domain.entities.client_note import ClientNote
from src.modules.clients.domain.value_objects.client_status import ClientStatus, ClientType
from src.modules.clients.domain.events.client_events import (
    ClientCreatedEvent,
    ClientStatusChangedEvent,
    ClientArchivedEvent,
    ClientDeletedEvent,
)


@dataclass
class ClientAggregate:
    client: Client
    contacts: list[ClientContact] = field(default_factory=list)
    notes: list[ClientNote] = field(default_factory=list)
    _pending_events: list[DomainEvent] = field(
        default_factory=list, init=False, repr=False, compare=False
    )

    @classmethod
    def create(
        cls,
        owner_user_id: uuid.UUID,
        full_name: str,
        client_type: ClientType = ClientType.INDIVIDUAL,
        email: str | None = None,
        phone: str | None = None,
        company_name: str | None = None,
    ) -> "ClientAggregate":
        now = datetime.now(timezone.utc)
        client_id = uuid.uuid4()
        client = Client(
            id=client_id,
            owner_user_id=owner_user_id,
            full_name=full_name.strip(),
            client_type=client_type,
            status=ClientStatus.PROSPECT,
            email=email,
            phone=phone,
            company_name=company_name,
            address=None,
            website=None,
            avatar_url=None,
            tags=[],
            created_at=now,
            updated_at=now,
            deleted_at=None,
        )
        agg = cls(client=client)
        agg._pending_events.append(
            ClientCreatedEvent(
                event_id=uuid.uuid4(),
                aggregate_id=client_id,
                occurred_at=now,
                owner_user_id=owner_user_id,
                full_name=full_name,
                email=email,
            )
        )
        return agg

    def add_contact(
        self,
        name: str,
        role: str | None = None,
        email: str | None = None,
        phone: str | None = None,
        is_primary: bool = False,
    ) -> ClientContact:
        contact = ClientContact(
            id=uuid.uuid4(),
            client_id=self.client.id,
            name=name.strip(),
            role=role,
            email=email,
            phone=phone,
            is_primary=is_primary,
            created_at=datetime.now(timezone.utc),
        )
        self.contacts.append(contact)
        return contact

    def add_note(self, content: str, author_user_id: uuid.UUID) -> ClientNote:
        note = ClientNote(
            id=uuid.uuid4(),
            client_id=self.client.id,
            author_user_id=author_user_id,
            content=content,
            created_at=datetime.now(timezone.utc),
        )
        self.notes.append(note)
        return note

    def change_status(self, target: ClientStatus) -> None:
        old_status = self.client.status
        self.client.change_status(target)
        now = datetime.now(timezone.utc)
        self._pending_events.append(
            ClientStatusChangedEvent(
                event_id=uuid.uuid4(),
                aggregate_id=self.client.id,
                occurred_at=now,
                old_status=old_status,
                new_status=target,
            )
        )
        if target == ClientStatus.ARCHIVED:
            self._pending_events.append(
                ClientArchivedEvent(
                    event_id=uuid.uuid4(),
                    aggregate_id=self.client.id,
                    occurred_at=now,
                    owner_user_id=self.client.owner_user_id,
                )
            )

    def delete(self) -> None:
        self.client.soft_delete()
        self._pending_events.append(
            ClientDeletedEvent(
                event_id=uuid.uuid4(),
                aggregate_id=self.client.id,
                occurred_at=self.client.updated_at,
                owner_user_id=self.client.owner_user_id,
            )
        )

    def pull_events(self) -> list[DomainEvent]:
        events = list(self._pending_events)
        self._pending_events.clear()
        return events
