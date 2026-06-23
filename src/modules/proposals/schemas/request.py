import uuid
from typing import Optional

from pydantic import BaseModel, Field


class ProposalRequest(BaseModel):
    deal_id: uuid.UUID
    content: dict
    status: str = "draft"


class ProposalStatusRequest(BaseModel):
    status: str = Field(..., description="Target status: sent, accepted, rejected, expired")


class AiProposalRequest(BaseModel):
    deal_id: uuid.UUID
    client_name: str
    company_name: Optional[str] = None
    project_type: str
    project_description: str
    estimated_scope: Optional[str] = None
    budget: Optional[str] = None
    urgency: Optional[str] = None
    service_category: str
    pricing_tier: str
    freelancer_name: str
