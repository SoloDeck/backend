from src.modules.contracts.domain.value_objects.contract_status import ContractStatus


class ContractDomainError(Exception):
    """Base for all Contract domain errors."""


class InvalidContractTransitionError(ContractDomainError):
    def __init__(self, from_status: ContractStatus, to_status: ContractStatus) -> None:
        super().__init__(
            f"Cannot transition contract from '{from_status.value}' to '{to_status.value}'"
        )


class TerminalContractError(ContractDomainError):
    def __init__(self, status: ContractStatus) -> None:
        super().__init__(f"Contract is in terminal status '{status.value}'")


class ContractEditForbiddenError(ContractDomainError):
    def __init__(self, status: ContractStatus) -> None:
        super().__init__(f"Contract cannot be edited in status '{status.value}'")


class MilestoneAlreadyCompletedError(ContractDomainError):
    def __init__(self, milestone_id: object) -> None:
        super().__init__(f"Milestone {milestone_id} is already completed")
