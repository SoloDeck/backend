from src.modules.subscriptions.domain.value_objects.entitlement import SubscriptionStatus


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
