import uuid
from dataclasses import dataclass
from datetime import datetime

from src.modules.deals.domain.value_objects.deal_stage import DealStage


@dataclass(frozen=True)
class DealStageHistory:
    """Immutable record of a single stage transition on a deal."""

    id: uuid.UUID
    deal_id: uuid.UUID
    from_stage: DealStage
    to_stage: DealStage
    transitioned_by: uuid.UUID  # owner_user_id
    transitioned_at: datetime
    note: str | None = None
