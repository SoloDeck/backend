"""Money value object — shared across deals, invoices, and contracts."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Money:
    amount: Decimal
    currency: str  # ISO 4217 three-letter code (e.g. "VND", "USD")

    def __post_init__(self) -> None:
        if self.amount < Decimal(0):
            raise ValueError(f"Money amount cannot be negative: {self.amount}")
        if len(self.currency) != 3 or not self.currency.isalpha():
            raise ValueError(f"Currency must be a 3-letter ISO 4217 code, got: {self.currency!r}")

    def add(self, other: "Money") -> "Money":
        self._assert_same_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def subtract(self, other: "Money") -> "Money":
        self._assert_same_currency(other)
        result = self.amount - other.amount
        if result < Decimal(0):
            raise ValueError("Subtraction would result in negative money")
        return Money(result, self.currency)

    def is_zero(self) -> bool:
        return self.amount == Decimal(0)

    def _assert_same_currency(self, other: "Money") -> None:
        if self.currency != other.currency:
            raise ValueError(
                f"Cannot operate on Money with different currencies: "
                f"{self.currency} vs {other.currency}"
            )

    @classmethod
    def zero(cls, currency: str = "VND") -> "Money":
        return cls(Decimal(0), currency)

    def __str__(self) -> str:
        return f"{self.amount} {self.currency}"
