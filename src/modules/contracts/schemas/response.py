import uuid
from datetime import date, datetime

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
    client_snapshot: dict
    effective_date: date | None
    end_date: date | None
    signed_by_freelancer_at: datetime | None
    signed_by_client_at: datetime | None
    share_token: str | None
    created_at: datetime
    updated_at: datetime


class ContractExportResponse(BaseModel):
    status: str
    task_id: str | None = None
    download_url: str | None = None
