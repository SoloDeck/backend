from src.modules.users.domain.value_objects.user_status import UserStatus


class UserDomainError(Exception):
    """Base for all User domain errors."""


class InvalidUserStatusTransitionError(UserDomainError):
    def __init__(self, from_status: UserStatus, to_status: UserStatus) -> None:
        super().__init__(
            f"Cannot transition user from '{from_status.value}' to '{to_status.value}'"
        )


class UserAlreadyDeletedError(UserDomainError):
    def __init__(self) -> None:
        super().__init__("User is already deleted")


class AdminRoleRequiredError(UserDomainError):
    def __init__(self) -> None:
        super().__init__("Only an admin can perform this action")
