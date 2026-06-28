import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from src.modules.subscriptions.domain.entities.subscription_plan import SubscriptionPlan
from src.modules.subscriptions.domain.value_objects.entitlement import (
    Entitlement,
    SubscriptionStatus,
)


@dataclass
class Subscription:
    id: uuid.UUID
    user_id: uuid.UUID
    plan: SubscriptionPlan
    status: SubscriptionStatus
    current_period_start: datetime
    current_period_end: datetime
    cancel_at_period_end: bool
    cancelled_at: datetime | None
    stripe_subscription_id: str | None
    stripe_customer_id: str | None
    override_by_admin_id: uuid.UUID | None
    override_expires_at: datetime | None
    created_at: datetime
    updated_at: datetime

    # ------------------------------------------------------------------ #
    # Queries                                                              #
    # ------------------------------------------------------------------ #

    @property
    def is_active(self) -> bool:
        return self.status == SubscriptionStatus.ACTIVE

    @property
    def is_suspended(self) -> bool:
        return self.status == SubscriptionStatus.SUSPENDED

    @property
    def entitlement(self) -> Entitlement:
        if self.is_suspended:
            return Entitlement(
                can_use_ai=False,
                can_export_pdf=False,
                max_clients=0,
                max_deals=0,
                max_ai_generations_per_month=0,
            )
        return self.plan.entitlement

    def check_entitlement(self, feature: str) -> None:
        """Check that the subscription grants access to a feature."""
        ent = self.entitlement
        if feature == "can_use_ai":
            ent.check_ai_access()
        elif feature == "can_export_pdf" and not ent.can_export_pdf:
            from src.modules.subscriptions.domain.value_objects.entitlement import (
                EntitlementViolationError,
            )

            raise EntitlementViolationError("PDF export requires a paid subscription")

    # ------------------------------------------------------------------ #
    # Commands                                                             #
    # ------------------------------------------------------------------ #

    def change_plan(self, new_plan: SubscriptionPlan) -> None:
        self.plan = new_plan
        self.updated_at = datetime.now(UTC)

    def suspend(self) -> None:
        from src.modules.subscriptions.domain.exceptions.exceptions import (
            InvalidSubscriptionTransitionError,
        )

        if self.status not in {SubscriptionStatus.ACTIVE, SubscriptionStatus.PAST_DUE}:
            raise InvalidSubscriptionTransitionError(self.status, SubscriptionStatus.SUSPENDED)
        self.status = SubscriptionStatus.SUSPENDED
        self.updated_at = datetime.now(UTC)

    def reactivate(self) -> None:
        from src.modules.subscriptions.domain.exceptions.exceptions import (
            InvalidSubscriptionTransitionError,
        )

        if self.status not in {SubscriptionStatus.SUSPENDED, SubscriptionStatus.PAST_DUE}:
            raise InvalidSubscriptionTransitionError(self.status, SubscriptionStatus.ACTIVE)
        self.status = SubscriptionStatus.ACTIVE
        self.updated_at = datetime.now(UTC)

    def cancel(self) -> None:
        self.status = SubscriptionStatus.CANCELLED
        self.cancelled_at = datetime.now(UTC)
        self.updated_at = self.cancelled_at

    def mark_past_due(self) -> None:
        self.status = SubscriptionStatus.PAST_DUE
        self.updated_at = datetime.now(UTC)
