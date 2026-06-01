from src.modules.deals.domain.value_objects.deal_stage import DealStage


class DealDomainError(Exception):
    """Base for all Deal domain errors."""


class InvalidStageTransitionError(DealDomainError):
    def __init__(self, from_stage: DealStage, to_stage: DealStage) -> None:
        super().__init__(
            f"Cannot transition deal from '{from_stage.value}' to '{to_stage.value}'"
        )
        self.from_stage = from_stage
        self.to_stage = to_stage


class TerminalDealError(DealDomainError):
    def __init__(self, stage: DealStage) -> None:
        super().__init__(
            f"Deal is in terminal stage '{stage.value}' — no further changes allowed"
        )
        self.stage = stage


class InvalidLeadScoreError(DealDomainError):
    def __init__(self, score: int) -> None:
        super().__init__(f"Lead score must be 0–100, got {score}")
        self.score = score


class DealNotFoundError(DealDomainError):
    def __init__(self, deal_id: object) -> None:
        super().__init__(f"Deal {deal_id} not found")
