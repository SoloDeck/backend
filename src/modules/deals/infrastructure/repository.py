from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession

@dataclass
class udealsRepository:
    db: AsyncSession
