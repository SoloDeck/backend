from src.modules.subscriptions.domain.value_objects.entitlement import SubscriptionStatus
from src.shared.exceptions.domain import DomainError


class SubscriptionDomainError(Exception):
    """Base for all Subscription domain errors."""


class InvalidSubscriptionTransitionError(SubscriptionDomainError):
    def __init__(self, from_status: SubscriptionStatus, to_status: SubscriptionStatus) -> None:
        super().__init__(
            f"Cannot transition subscription from '{from_status.value}' to '{to_status.value}'"
        )


class DuplicateSubscriptionError(SubscriptionDomainError):
    def __init__(self, user_id: object) -> None:
        super().__init__(f"User {user_id} already has a subscription")


class EntitlementViolationError(SubscriptionDomainError):
    def __init__(self, message: str) -> None:
        super().__init__(message)


# Payment errors subclass the shared DomainError (not SubscriptionDomainError
# above) so they get real HTTP translation via src/shared/exceptions/http.py's
# generic DomainError fallback (400) — SubscriptionDomainError isn't wired to
# any exception handler.


class PlanNotPurchasableError(DomainError):
    def __init__(self, message: str = "This plan cannot be purchased") -> None:
        super().__init__(message)


class SubscriptionNotCancellableError(DomainError):
    def __init__(self, message: str = "Subscription cannot be cancelled") -> None:
        super().__init__(message)


class InvalidPaymentSignatureError(DomainError):
    def __init__(self, message: str = "Payment callback signature verification failed") -> None:
        super().__init__(message)
