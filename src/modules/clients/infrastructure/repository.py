from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession

@dataclass
class uclientsRepository:
    db: AsyncSession
