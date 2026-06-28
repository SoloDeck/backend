from pydantic import BaseModel


class LeadQualificationRequest(BaseModel):
    inquiry_text: str
