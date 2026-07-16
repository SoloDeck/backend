import uuid
from typing import Literal

from pydantic import BaseModel, Field

AiJobType = Literal["lead_qualifier", "proposal_generator", "contract_generator"]
AiJobEntityType = Literal["deal", "contract"]


class CreateAiJobRequest(BaseModel):
    entity_id: uuid.UUID
    type: AiJobType
    entity_type: AiJobEntityType
    idempotency_key: str | None = Field(default=None, max_length=255)
