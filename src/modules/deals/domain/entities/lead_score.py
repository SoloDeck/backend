import uuid
from dataclasses import dataclass
from datetime import datetime

from src.modules.deals.domain.value_objects.ai_confidence import AIConfidence


@dataclass
class LeadScore:
    """AI-generated qualification score for a deal.

    Every LeadScore belongs to exactly one Deal. Score is 0–100.
    Confidence is 0.0–1.0.
    """

    id: uuid.UUID
    deal_id: uuid.UUID
    score: int  # 0–100
    confidence: AIConfidence
    reasoning: str
    model_version: str
    generated_at: datetime

    def __post_init__(self) -> None:
        if not 0 <= self.score <= 100:
            raise ValueError(f"Score must be 0–100, got {self.score}")
        if not self.reasoning.strip():
            raise ValueError("Reasoning must not be empty")

    @property
    def is_qualified(self) -> bool:
        """Conventionally, ≥60 score means the lead is worth pursuing."""
        return self.score >= 60

    @property
    def level(self) -> str:
        if self.score >= 80:
            return "hot"
        if self.score >= 50:
            return "warm"
        return "cold"
