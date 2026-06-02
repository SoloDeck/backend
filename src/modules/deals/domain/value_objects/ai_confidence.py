from dataclasses import dataclass


@dataclass(frozen=True)
class AIConfidence:
    """Confidence score of an AI-generated prediction. Always 0.0–1.0."""

    value: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.value <= 1.0:
            raise ValueError(
                f"AIConfidence must be between 0.0 and 1.0, got {self.value}"
            )

    @property
    def level(self) -> str:
        if self.value >= 0.7:
            return "high"
        if self.value >= 0.4:
            return "medium"
        return "low"

    @classmethod
    def high(cls) -> "AIConfidence":
        return cls(0.85)

    @classmethod
    def medium(cls) -> "AIConfidence":
        return cls(0.55)

    @classmethod
    def low(cls) -> "AIConfidence":
        return cls(0.25)
