"""Auth infrastructure — database access for tokens and OAuth identities."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class AuthRepository:
    db: AsyncSession
