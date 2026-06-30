
from pydantic import BaseModel


class ProposalContent(BaseModel):
    project_overview: str

    scope_of_work: list[str]

    deliverables: list[str]

    timeline: str

    pricing: str

    payment_terms: str

    assumptions: str
