import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from src.modules.clients.domain.value_objects.client_status import (
    CLIENT_STATUS_TRANSITIONS,
    ClientStatus,
    ClientType,
)


@dataclass
class Client:
    id: uuid.UUID
    owner_user_id: uuid.UUID
    full_name: str
    client_type: ClientType
    status: ClientStatus
    email: str | None
    phone: str | None
    company_name: str | None
    address: str | None
    website: str | None
    avatar_url: str | None
    tags: list[str]
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None

    MAX_TAGS = 20

    # ------------------------------------------------------------------ #
    # Queries                                                              #
    # ------------------------------------------------------------------ #

    @property
    def is_archived(self) -> bool:
        return self.status == ClientStatus.ARCHIVED

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def can_transition_to(self, target: ClientStatus) -> bool:
        return target in CLIENT_STATUS_TRANSITIONS[self.status]

    # ------------------------------------------------------------------ #
    # Commands                                                             #
    # ------------------------------------------------------------------ #

    def change_status(self, target: ClientStatus) -> None:
        from src.modules.clients.domain.exceptions.exceptions import (
            ArchivedClientError,
            InvalidClientStatusTransitionError,
        )
        if self.is_archived:
            raise ArchivedClientError()
        if not self.can_transition_to(target):
            raise InvalidClientStatusTransitionError(self.status, target)
        self.status = target
        self.updated_at = datetime.now(UTC)

    def update_contact_info(
        self,
        full_name: str | None = None,
        email: str | None = None,
        phone: str | None = None,
        company_name: str | None = None,
        address: str | None = None,
        website: str | None = None,
    ) -> None:
        from src.modules.clients.domain.exceptions.exceptions import ArchivedClientError
        if self.is_archived:
            raise ArchivedClientError()
        if full_name is not None:
            if not full_name.strip():
                raise ValueError("Client name must not be blank")
            self.full_name = full_name.strip()
        if email is not None:
            self.email = email
        if phone is not None:
            self.phone = phone
        if company_name is not None:
            self.company_name = company_name
        if address is not None:
            self.address = address
        if website is not None:
            self.website = website
        self.updated_at = datetime.now(UTC)

    def add_tag(self, tag: str) -> None:
        from src.modules.clients.domain.exceptions.exceptions import ArchivedClientError
        if self.is_archived:
            raise ArchivedClientError()
        normalized = tag.strip().lower()
        if not normalized:
            raise ValueError("Tag must not be blank")
        if len(self.tags) >= self.MAX_TAGS:
            raise ValueError(f"Client cannot have more than {self.MAX_TAGS} tags")
        if normalized not in self.tags:
            self.tags.append(normalized)
            self.updated_at = datetime.now(UTC)

    def remove_tag(self, tag: str) -> None:
        normalized = tag.strip().lower()
        if normalized in self.tags:
            self.tags.remove(normalized)
            self.updated_at = datetime.now(UTC)

    def archive(self) -> None:
        self.change_status(ClientStatus.ARCHIVED)

    def soft_delete(self) -> None:
        self.deleted_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)
