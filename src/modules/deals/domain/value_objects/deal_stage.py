from enum import StrEnum


class DealStage(StrEnum):
    NEW_LEAD = "new_lead"
    QUALIFIED = "qualified"
    PROPOSAL_SENT = "proposal_sent"
    IN_NEGOTIATION = "in_negotiation"
    ACTIVE = "active"
    COMPLETED_AND_BILLED = "completed_and_billed"
    LOST = "lost"


# Allowed forward (and occasional backward) transitions per stage.
STAGE_TRANSITIONS: dict[DealStage, frozenset[DealStage]] = {
    DealStage.NEW_LEAD: frozenset({DealStage.QUALIFIED, DealStage.LOST}),
    DealStage.QUALIFIED: frozenset({DealStage.PROPOSAL_SENT, DealStage.LOST}),
    DealStage.PROPOSAL_SENT: frozenset({DealStage.IN_NEGOTIATION, DealStage.LOST}),
    DealStage.IN_NEGOTIATION: frozenset({DealStage.ACTIVE, DealStage.LOST}),
    DealStage.ACTIVE: frozenset({DealStage.COMPLETED_AND_BILLED, DealStage.LOST}),
    DealStage.COMPLETED_AND_BILLED: frozenset(),
    DealStage.LOST: frozenset(),
}

TERMINAL_STAGES: frozenset[DealStage] = frozenset({DealStage.COMPLETED_AND_BILLED, DealStage.LOST})
