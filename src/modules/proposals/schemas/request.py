import uuid

from pydantic import BaseModel, Field


class ProposalRequest(BaseModel):
    deal_id: uuid.UUID
    content: dict
    status: str = "draft"


class ProposalStatusRequest(BaseModel):
    status: str = Field(..., description="Target status: sent, accepted, rejected, expired")
