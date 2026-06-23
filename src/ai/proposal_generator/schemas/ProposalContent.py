from pydantic import BaseModel
from typing import List

class ProposalContent(BaseModel):
    project_overview: str

    scope_of_work: List[str]

    deliverables: List[str]

    timeline: str

    pricing: str

    payment_terms: str

    assumptions: List[str]