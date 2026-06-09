from abc import ABC, abstractmethod

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


class BaseSeeder(ABC):
    """Abstract base for all seeders.

    Each seeder must be idempotent — running it multiple times produces
    the same database state as running it once.  Use INSERT ... ON CONFLICT
    DO NOTHING or SELECT-before-insert patterns to guarantee this.
    """

    name: str = "unnamed"

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._log = logger.bind(seeder=self.name)

    @abstractmethod
    async def run(self) -> None:
        """Execute the seeder.  Must be idempotent."""

    async def _commit(self) -> None:
        await self.db.commit()
        self._log.info("seeder.committed")
