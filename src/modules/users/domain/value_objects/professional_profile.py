from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ProfessionalProfile:
    skills: tuple[str, ...]         # immutable tuple
    specialization: str | None
    default_hourly_rate: Decimal | None
    currency: str                   # ISO 4217
    portfolio_url: str | None
    business_name: str | None

    def __post_init__(self) -> None:
        if self.default_hourly_rate is not None and self.default_hourly_rate < Decimal(0):
            raise ValueError("Hourly rate cannot be negative")
        if len(self.currency) != 3 or not self.currency.isalpha():
            raise ValueError(f"Currency must be 3-letter ISO 4217 code, got {self.currency!r}")

    @classmethod
    def empty(cls, currency: str = "VND") -> "ProfessionalProfile":
        return cls(
            skills=(),
            specialization=None,
            default_hourly_rate=None,
            currency=currency,
            portfolio_url=None,
            business_name=None,
        )

    def with_skills(self, skills: list[str]) -> "ProfessionalProfile":
        return ProfessionalProfile(
            skills=tuple(s.strip() for s in skills if s.strip()),
            specialization=self.specialization,
            default_hourly_rate=self.default_hourly_rate,
            currency=self.currency,
            portfolio_url=self.portfolio_url,
            business_name=self.business_name,
        )
