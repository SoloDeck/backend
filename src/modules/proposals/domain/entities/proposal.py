import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from src.modules.proposals.domain.value_objects.proposal_status import (
    ProposalStatus,
    PROPOSAL_TRANSITIONS,
    TERMINAL_PROPOSAL_STATUSES,
)
from src.shared.domain.value_objects.money import Money


@dataclass
class Proposal:
    id: uuid.UUID
    deal_id: uuid.UUID              # immutable
    owner_user_id: uuid.UUID
    version: int                    # 1-based, incremented on revision
    status: ProposalStatus
    title: str
    content: dict[str, object]      # structured JSONB (sections, line items)
    total_value: Money
    valid_until: datetime | None
    share_token: str | None
    share_token_expires_at: datetime | None
    ai_generated: bool
    sent_at: datetime | None
    accepted_at: datetime | None
    rejected_at: datetime | None
    rejection_reason: str | None
    created_at: datetime
    updated_at: datetime

    # ------------------------------------------------------------------ #
    # Queries                                                              #
    # ------------------------------------------------------------------ #

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_PROPOSAL_STATUSES

    @property
    def is_editable(self) -> bool:
        return self.status == ProposalStatus.DRAFT

    def can_transition_to(self, target: ProposalStatus) -> bool:
        return target in PROPOSAL_TRANSITIONS[self.status]

    # ------------------------------------------------------------------ #
    # Commands                                                             #
    # ------------------------------------------------------------------ #

    def update_content(self, content: dict[str, object], total_value: Money) -> None:
        from src.modules.proposals.domain.exceptions.exceptions import ProposalEditForbiddenError
        if not self.is_editable:
            raise ProposalEditForbiddenError(self.status)
        self.content = content
        self.total_value = total_value
        self.updated_at = datetime.now(timezone.utc)

    def send(self) -> None:
        from src.modules.proposals.domain.exceptions.exceptions import (
            InvalidProposalTransitionError,
        )
        if not self.can_transition_to(ProposalStatus.SENT):
            raise InvalidProposalTransitionError(self.status, ProposalStatus.SENT)
        if self.total_value.is_zero():
            raise ValueError("Cannot send a proposal with zero value")
        self.status = ProposalStatus.SENT
        self.sent_at = datetime.now(timezone.utc)
        self.updated_at = self.sent_at

    def accept(self) -> None:
        from src.modules.proposals.domain.exceptions.exceptions import (
            InvalidProposalTransitionError,
        )
        if not self.can_transition_to(ProposalStatus.ACCEPTED):
            raise InvalidProposalTransitionError(self.status, ProposalStatus.ACCEPTED)
        now = datetime.now(timezone.utc)
        self.status = ProposalStatus.ACCEPTED
        self.accepted_at = now
        self.updated_at = now

    def reject(self, reason: str | None = None) -> None:
        from src.modules.proposals.domain.exceptions.exceptions import (
            InvalidProposalTransitionError,
        )
        if not self.can_transition_to(ProposalStatus.REJECTED):
            raise InvalidProposalTransitionError(self.status, ProposalStatus.REJECTED)
        now = datetime.now(timezone.utc)
        self.status = ProposalStatus.REJECTED
        self.rejection_reason = reason
        self.rejected_at = now
        self.updated_at = now

    def expire(self) -> None:
        from src.modules.proposals.domain.exceptions.exceptions import (
            InvalidProposalTransitionError,
        )
        if not self.can_transition_to(ProposalStatus.EXPIRED):
            raise InvalidProposalTransitionError(self.status, ProposalStatus.EXPIRED)
        self.status = ProposalStatus.EXPIRED
        self.updated_at = datetime.now(timezone.utc)

    def supersede(self) -> None:
        """Mark this proposal as superseded by a newer version."""
        self.status = ProposalStatus.SUPERSEDED
        self.updated_at = datetime.now(timezone.utc)
