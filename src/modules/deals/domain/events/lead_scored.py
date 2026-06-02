import uuid
from dataclasses import dataclass

from src.shared.domain.base import DomainEvent


@dataclass(frozen=True)
class LeadScoredEvent(DomainEvent):
    score: int
    confidence: float
    recommendation: str | None
    model_version: str
