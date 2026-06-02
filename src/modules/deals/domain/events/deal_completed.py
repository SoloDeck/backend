from dataclasses import dataclass
from datetime import datetime

from src.shared.domain.base import DomainEvent


@dataclass(frozen=True)
class DealCompletedEvent(DomainEvent):
    """Emitted when a deal reaches a terminal stage (won or lost)."""

    outcome: str        # "won" | "lost"
    closed_at: datetime
