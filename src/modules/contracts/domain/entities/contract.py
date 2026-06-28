import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from src.modules.contracts.domain.value_objects.contract_status import (
    CONTRACT_TRANSITIONS,
    TERMINAL_CONTRACT_STATUSES,
    ContractStatus,
)


@dataclass
class Contract:
    id: uuid.UUID
    deal_id: uuid.UUID  # immutable
    proposal_id: uuid.UUID  # immutable
    owner_user_id: uuid.UUID
    status: ContractStatus
    title: str
    content: dict[str, object]
    client_snapshot: dict[str, object]  # point-in-time copy of client; never updated
    ai_generated: bool
    signed_at: datetime | None
    completed_at: datetime | None
    terminated_at: datetime | None
    termination_reason: str | None
    share_token: str | None
    share_token_expires_at: datetime | None
    created_at: datetime
    updated_at: datetime

    # ------------------------------------------------------------------ #
    # Queries                                                              #
    # ------------------------------------------------------------------ #

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_CONTRACT_STATUSES

    @property
    def is_editable(self) -> bool:
        return self.status == ContractStatus.DRAFT

    def can_transition_to(self, target: ContractStatus) -> bool:
        return target in CONTRACT_TRANSITIONS[self.status]

    # ------------------------------------------------------------------ #
    # Commands                                                             #
    # ------------------------------------------------------------------ #

    def send_for_signature(self) -> None:
        from src.modules.contracts.domain.exceptions.exceptions import (
            InvalidContractTransitionError,
        )

        if not self.can_transition_to(ContractStatus.PENDING_SIGNATURES):
            raise InvalidContractTransitionError(self.status, ContractStatus.PENDING_SIGNATURES)
        self.status = ContractStatus.PENDING_SIGNATURES
        self.updated_at = datetime.now(UTC)

    def sign(self) -> None:
        from src.modules.contracts.domain.exceptions.exceptions import (
            InvalidContractTransitionError,
        )

        if not self.can_transition_to(ContractStatus.ACTIVE):
            raise InvalidContractTransitionError(self.status, ContractStatus.ACTIVE)
        now = datetime.now(UTC)
        self.status = ContractStatus.ACTIVE
        self.signed_at = now
        self.updated_at = now

    def complete(self) -> None:
        from src.modules.contracts.domain.exceptions.exceptions import (
            InvalidContractTransitionError,
        )

        if not self.can_transition_to(ContractStatus.COMPLETED):
            raise InvalidContractTransitionError(self.status, ContractStatus.COMPLETED)
        now = datetime.now(UTC)
        self.status = ContractStatus.COMPLETED
        self.completed_at = now
        self.updated_at = now

    def terminate(self, reason: str | None = None) -> None:
        from src.modules.contracts.domain.exceptions.exceptions import (
            InvalidContractTransitionError,
        )

        if not self.can_transition_to(ContractStatus.TERMINATED):
            raise InvalidContractTransitionError(self.status, ContractStatus.TERMINATED)
        now = datetime.now(UTC)
        self.status = ContractStatus.TERMINATED
        self.terminated_at = now
        self.termination_reason = reason
        self.updated_at = now

    def update_content(self, content: dict[str, object]) -> None:
        from src.modules.contracts.domain.exceptions.exceptions import ContractEditForbiddenError

        if not self.is_editable:
            raise ContractEditForbiddenError(self.status)
        self.content = content
        self.updated_at = datetime.now(UTC)
