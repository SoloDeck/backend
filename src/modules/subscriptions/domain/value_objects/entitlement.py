from dataclasses import dataclass
from enum import Enum


class SubscriptionStatus(str, Enum):
    ACTIVE = "active"
    PAST_DUE = "past_due"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class Entitlement:
    """Derived entitlements from a subscription plan.

    Checked before every AI call and resource creation.
    """

    can_use_ai: bool
    can_export_pdf: bool
    max_clients: int | None         # None = unlimited
    max_deals: int | None           # None = unlimited
    max_ai_generations_per_month: int  # 0 = unlimited

    def check_ai_access(self) -> None:
        """Raise if AI features are not available."""
        if not self.can_use_ai:
            raise EntitlementViolationError(
                "AI features require a paid subscription"
            )

    def check_client_limit(self, current_count: int) -> None:
        if self.max_clients is not None and current_count >= self.max_clients:
            raise EntitlementViolationError(
                f"Client limit of {self.max_clients} reached. Upgrade to add more clients."
            )

    def check_deal_limit(self, current_count: int) -> None:
        if self.max_deals is not None and current_count >= self.max_deals:
            raise EntitlementViolationError(
                f"Deal limit of {self.max_deals} reached. Upgrade to add more deals."
            )

    def check_ai_generation_limit(self, used_this_period: int) -> None:
        if self.max_ai_generations_per_month == 0:
            return  # unlimited
        if used_this_period >= self.max_ai_generations_per_month:
            raise EntitlementViolationError(
                f"Monthly AI generation limit of {self.max_ai_generations_per_month} reached."
            )


class EntitlementViolationError(Exception):
    """Raised when an entitlement check fails."""
