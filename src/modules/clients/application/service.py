"""Clients application service — skeleton."""
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession

@dataclass
class ClientsService:
    db: AsyncSession
