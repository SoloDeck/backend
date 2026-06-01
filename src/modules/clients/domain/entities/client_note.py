import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ClientNote:
    """Append-only note on a client. Never updated after creation."""

    id: uuid.UUID
    client_id: uuid.UUID
    author_user_id: uuid.UUID
    content: str
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.content.strip():
            raise ValueError("Note content must not be blank")
