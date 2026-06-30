import uuid

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
    company_name: str | None = None
    project_type: str
    project_description: str
    estimated_scope: str | None = None
    budget: str | None = None
    urgency: str | None = None
    service_category: str
    pricing_tier: str
    freelancer_name: str
