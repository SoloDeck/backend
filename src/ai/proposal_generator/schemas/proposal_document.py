
from pydantic import BaseModel


class ProposalDocument(BaseModel):
    freelancer_name: str

    client_name: str

    company_name: str | None = None

    project_type: str

    proposal_date: str

    project_overview: str

    scope_of_work: list[str]

    deliverables: list[str]

    timeline: str

    pricing: str

    payment_terms: str

    assumptions: str
