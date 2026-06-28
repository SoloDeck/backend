
from pydantic import BaseModel


class ProposalGenerationInput(BaseModel):
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
