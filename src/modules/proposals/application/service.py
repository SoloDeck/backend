"""Proposals application service — skeleton."""
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession

@dataclass
class ProposalsService:
    db: AsyncSession
