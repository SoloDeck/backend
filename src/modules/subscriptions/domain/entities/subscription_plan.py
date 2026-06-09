import uuid
from dataclasses import dataclass

from src.modules.subscriptions.domain.value_objects.entitlement import Entitlement
from src.shared.domain.value_objects.money import Money


@dataclass(frozen=True)
class SubscriptionPlan:
    id: uuid.UUID
    name: str
    slug: str
    price_monthly: Money
    entitlement: Entitlement
    is_active: bool

    @property
    def is_free(self) -> bool:
        return self.price_monthly.is_zero()
