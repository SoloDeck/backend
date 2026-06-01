import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ClientContact:
    """Additional contact person on a client (e.g. finance, technical)."""

    id: uuid.UUID
    client_id: uuid.UUID
    name: str
    role: str | None
    email: str | None
    phone: str | None
    is_primary: bool
    created_at: datetime
