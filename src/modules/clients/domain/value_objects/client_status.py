from enum import Enum


class ClientStatus(str, Enum):
    PROSPECT = "prospect"
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


class ClientType(str, Enum):
    INDIVIDUAL = "individual"
    COMPANY = "company"


TERMINAL_CLIENT_STATUSES: frozenset[ClientStatus] = frozenset({ClientStatus.ARCHIVED})

CLIENT_STATUS_TRANSITIONS: dict[ClientStatus, frozenset[ClientStatus]] = {
    ClientStatus.PROSPECT: frozenset({ClientStatus.ACTIVE, ClientStatus.ARCHIVED}),
    ClientStatus.ACTIVE: frozenset({ClientStatus.INACTIVE, ClientStatus.ARCHIVED}),
    ClientStatus.INACTIVE: frozenset({ClientStatus.ACTIVE, ClientStatus.ARCHIVED}),
    ClientStatus.ARCHIVED: frozenset(),
}
