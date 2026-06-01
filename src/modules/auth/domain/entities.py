"""Auth domain value objects and entities."""

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Credential:
    user_id: uuid.UUID
    email: str
    hashed_password: str


@dataclass(frozen=True)
class OAuthIdentity:
    user_id: uuid.UUID
    provider: str
    provider_sub: str
    provider_email: str | None


@dataclass(frozen=True)
class RefreshToken:
    id: uuid.UUID
    user_id: uuid.UUID
    token_hash: str
    expires_at: datetime
    revoked_at: datetime | None
