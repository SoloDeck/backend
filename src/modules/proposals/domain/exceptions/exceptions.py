from src.modules.proposals.domain.value_objects.proposal_status import ProposalStatus


class ProposalDomainError(Exception):
    """Base for all Proposal domain errors."""


class InvalidProposalTransitionError(ProposalDomainError):
    def __init__(self, from_status: ProposalStatus, to_status: ProposalStatus) -> None:
        super().__init__(
            f"Cannot transition proposal from '{from_status.value}' to '{to_status.value}'"
        )


class TerminalProposalError(ProposalDomainError):
    def __init__(self, status: ProposalStatus) -> None:
        super().__init__(f"Proposal is in terminal status '{status.value}'")


class ProposalEditForbiddenError(ProposalDomainError):
    def __init__(self, status: ProposalStatus) -> None:
        super().__init__(f"Proposal content cannot be edited in status '{status.value}'")
