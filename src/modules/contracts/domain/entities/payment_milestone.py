import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from src.shared.domain.value_objects.money import Money


@dataclass
class PaymentMilestone:
    id: uuid.UUID
    contract_id: uuid.UUID
    title: str
    description: str | None
    amount: Money
    due_date: datetime | None
    completed_at: datetime | None

    @property
    def is_completed(self) -> bool:
        return self.completed_at is not None

    def complete(self) -> None:
        from src.modules.contracts.domain.exceptions.exceptions import (
            MilestoneAlreadyCompletedError,
        )

        if self.is_completed:
            raise MilestoneAlreadyCompletedError(self.id)
        self.completed_at = datetime.now(UTC)
