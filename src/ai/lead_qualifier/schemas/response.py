from pydantic import BaseModel


class DetectedSignal(BaseModel):
    text: str
    is_positive: bool


class LeadQualificationResponse(BaseModel):
    project_type: str
    budget_signal: str
    timeline_signal: str
    urgency_signal: str
    red_flags: list[str]
    suggested_lead_score: str
    reasoning: str
    next_step: str | None = None
    detected_signals: list[DetectedSignal] | None = None
    suggested_actions: list[str] | None = None
    price_range_min: int | None = None
    price_range_max: int | None = None
