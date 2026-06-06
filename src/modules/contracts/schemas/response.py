import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ContractResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    deal_id: uuid.UUID
    proposal_id: uuid.UUID
    client_id: uuid.UUID
    owner_user_id: uuid.UUID
    version_number: int
    status: str
    content: dict
    share_token: str | None
    created_at: datetime
    updated_at: datetime
