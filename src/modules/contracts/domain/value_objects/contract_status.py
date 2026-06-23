from enum import StrEnum


class ContractStatus(StrEnum):
    DRAFT = "draft"
    PENDING_SIGNATURES = "pending_signatures"
    ACTIVE = "active"
    COMPLETED = "completed"
    TERMINATED = "terminated"
    EXPIRED = "expired"
    ARCHIVED = "archived"


TERMINAL_CONTRACT_STATUSES: frozenset[ContractStatus] = frozenset(
    {ContractStatus.COMPLETED, ContractStatus.TERMINATED, ContractStatus.EXPIRED, ContractStatus.ARCHIVED}
)

CONTRACT_TRANSITIONS: dict[ContractStatus, frozenset[ContractStatus]] = {
    ContractStatus.DRAFT: frozenset({ContractStatus.PENDING_SIGNATURES}),
    ContractStatus.PENDING_SIGNATURES: frozenset({ContractStatus.ACTIVE, ContractStatus.EXPIRED}),
    ContractStatus.ACTIVE: frozenset({ContractStatus.COMPLETED, ContractStatus.TERMINATED, ContractStatus.ARCHIVED}),
    ContractStatus.COMPLETED: frozenset(),
    ContractStatus.TERMINATED: frozenset(),
    ContractStatus.EXPIRED: frozenset(),
    ContractStatus.ARCHIVED: frozenset(),
}
