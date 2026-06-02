from src.modules.clients.domain.value_objects.client_status import ClientStatus


class ClientDomainError(Exception):
    """Base for all Client domain errors."""


class InvalidClientStatusTransitionError(ClientDomainError):
    def __init__(self, from_status: ClientStatus, to_status: ClientStatus) -> None:
        super().__init__(
            f"Cannot transition client from '{from_status.value}' to '{to_status.value}'"
        )


class ArchivedClientError(ClientDomainError):
    def __init__(self) -> None:
        super().__init__("Client is archived — no further changes allowed")


class DuplicateClientEmailError(ClientDomainError):
    def __init__(self, email: str) -> None:
        super().__init__(f"A client with email '{email}' already exists for this owner")


class ClientNotFoundError(ClientDomainError):
    def __init__(self, client_id: object) -> None:
        super().__init__(f"Client {client_id} not found")
