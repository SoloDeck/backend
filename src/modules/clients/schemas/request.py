from datetime import datetime

from pydantic import BaseModel, Field

from src.modules.clients.domain.value_objects.client_status import ClientStatus, ClientType


class ClientRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: str | None = None
    phone: str | None = None
    type: ClientType = ClientType.INDIVIDUAL
    website: str | None = None
    linkedin_url: str | None = None
    address_city: str | None = None
    address_country: str | None = None
    status: ClientStatus = ClientStatus.PROSPECT
    notes: str | None = None
    description: str | None = None


class ClientUpdateRequest(BaseModel):
    """Partial update — every field is optional and omitted fields are left untouched.

    Distinct from ClientRequest (create): that schema's `type`/`status` defaults
    ("individual"/"prospect") are correct for a new client, but the same defaults
    on a PATCH body silently reset an existing client's real type/status back to
    them whenever the caller omits those fields — this schema's None defaults are
    what let the service layer's `if value is not None` skip actually work.
    """

    name: str | None = Field(default=None, min_length=1, max_length=255)
    email: str | None = None
    phone: str | None = None
    type: ClientType | None = None
    website: str | None = None
    linkedin_url: str | None = None
    address_city: str | None = None
    address_country: str | None = None
    status: ClientStatus | None = None
    notes: str | None = None
    description: str | None = None


class CommLogRequest(BaseModel):
    channel: str
    summary: str
    communicated_at: datetime


class TagRequest(BaseModel):
    tag: str
