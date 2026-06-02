from enum import Enum


class ProposalStatus(str, Enum):
    DRAFT = "draft"
    SENT = "sent"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"


TERMINAL_PROPOSAL_STATUSES: frozenset[ProposalStatus] = frozenset(
    {
        ProposalStatus.ACCEPTED,
        ProposalStatus.REJECTED,
        ProposalStatus.EXPIRED,
        ProposalStatus.SUPERSEDED,
    }
)

PROPOSAL_TRANSITIONS: dict[ProposalStatus, frozenset[ProposalStatus]] = {
    ProposalStatus.DRAFT: frozenset({ProposalStatus.SENT, ProposalStatus.SUPERSEDED}),
    ProposalStatus.SENT: frozenset(
        {
            ProposalStatus.ACCEPTED,
            ProposalStatus.REJECTED,
            ProposalStatus.EXPIRED,
            ProposalStatus.SUPERSEDED,
        }
    ),
    ProposalStatus.ACCEPTED: frozenset(),
    ProposalStatus.REJECTED: frozenset(),
    ProposalStatus.EXPIRED: frozenset(),
    ProposalStatus.SUPERSEDED: frozenset(),
}
