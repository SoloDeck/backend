import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class UsageFeature(str, Enum):
    AI_LEAD_QUALIFY = "ai_lead_qualify"
    AI_PROPOSAL_GENERATE = "ai_proposal_generate"
    AI_CONTRACT_GENERATE = "ai_contract_generate"
    AI_FOLLOWUP_GENERATE = "ai_followup_generate"
    PDF_EXPORT = "pdf_export"


@dataclass(frozen=True)
class UsageRecord:
    """Append-only record of a single feature usage event."""

    id: uuid.UUID
    user_id: uuid.UUID
    subscription_id: uuid.UUID
    feature: UsageFeature
    used_at: datetime
    period_start: datetime
    period_end: datetime
    tokens_used: int | None         # for AI features
    cost_usd: float | None
