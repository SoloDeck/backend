import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AiJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: str
    entity_type: str
    entity_id: uuid.UUID
    status: str
    result: dict[str, object] | None
    error: dict[str, object] | None
    created_at: datetime
    updated_at: datetime
