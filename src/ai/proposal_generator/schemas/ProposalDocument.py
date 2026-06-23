from pydantic import BaseModel
from typing import Optional

class ProposalGenerationInput(BaseModel):
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