from pydantic import BaseModel
from typing import List



class LeadQualificationResponse(BaseModel):
    project_type: str
    budget_signal: str
    timeline_signal: str
    urgency_signal: str
    red_flags: List[str]
    suggested_lead_score: str