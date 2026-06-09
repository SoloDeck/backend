import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class DealActivityType(StrEnum):
    STAGE_CHANGE = "stage_change"
    NOTE_ADDED = "note_added"
    DOCUMENT_ATTACHED = "document_attached"
    AI_QUALIFICATION = "ai_qualification"


@dataclass(frozen=True)
class DealActivity:
    """Append-only audit log entry for a deal.

    Never updated — only inserted.
    """

    id: uuid.UUID
    deal_id: uuid.UUID
    owner_user_id: uuid.UUID
    activity_type: DealActivityType
    description: str
    occurred_at: datetime
    metadata: dict[str, object] | None = None
