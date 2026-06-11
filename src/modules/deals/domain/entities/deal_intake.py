import uuid
from dataclasses import dataclass
from datetime import datetime

@dataclass
class DealIntake:
    id: uuid.UUID
    owner_user_id: uuid.UUID
    client_id: uuid.UUID

    inquiry_text: str

    estimated_budget: str | None
    desired_timeline: str | None

    source: str | None

    submitted_at: datetime
    created_at: datetime