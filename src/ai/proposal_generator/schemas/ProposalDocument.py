from pydantic import BaseModel
from typing import List, Optional

class ProposalDocument(BaseModel):
    freelancer_name: str

    client_name: str

    company_name: Optional[str] = None

    project_type: str

    proposal_date: str

    project_overview: str

    scope_of_work: List[str]

    deliverables: List[str]

    timeline: str

    pricing: str

    payment_terms: str

    assumptions: str