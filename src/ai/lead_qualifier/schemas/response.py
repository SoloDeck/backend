
from pydantic import BaseModel


class LeadQualificationResponse(BaseModel):
    project_type: str
    budget_signal: str
    timeline_signal: str
    urgency_signal: str
    red_flags: list[str]
    suggested_lead_score: str
    reasoning: str
