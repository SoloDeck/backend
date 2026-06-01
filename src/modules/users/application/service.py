"""Users application service.

Responsibilities:
- Create and store user accounts
- Manage user profile (identity, professional profile, preferences)
- Soft-delete user accounts
- Email change flow
"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class UsersService:
    db: AsyncSession
