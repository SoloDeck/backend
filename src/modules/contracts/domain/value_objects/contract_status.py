from enum import Enum


class ContractStatus(str, Enum):
    DRAFT = "draft"
    PENDING_SIGNATURES = "pending_signatures"
    ACTIVE = "active"
    COMPLETED = "completed"
    TERMINATED = "terminated"
    EXPIRED = "expired"


TERMINAL_CONTRACT_STATUSES: frozenset[ContractStatus] = frozenset(
    {ContractStatus.COMPLETED, ContractStatus.TERMINATED, ContractStatus.EXPIRED}
)

CONTRACT_TRANSITIONS: dict[ContractStatus, frozenset[ContractStatus]] = {
    ContractStatus.DRAFT: frozenset({ContractStatus.PENDING_SIGNATURES}),
    ContractStatus.PENDING_SIGNATURES: frozenset({ContractStatus.ACTIVE, ContractStatus.EXPIRED}),
    ContractStatus.ACTIVE: frozenset({ContractStatus.COMPLETED, ContractStatus.TERMINATED}),
    ContractStatus.COMPLETED: frozenset(),
    ContractStatus.TERMINATED: frozenset(),
    ContractStatus.EXPIRED: frozenset(),
}
