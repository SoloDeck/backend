from datetime import datetime

from pydantic import BaseModel


class ClientRequest(BaseModel):
    name: str
    email: str | None = None
    phone: str | None = None
    type: str = "individual"
    website: str | None = None
    linkedin_url: str | None = None
    address_city: str | None = None
    address_country: str | None = None
    status: str = "prospect"
    notes: str | None = None
    description: str | None = None


class CommLogRequest(BaseModel):
    channel: str
    summary: str
    communicated_at: datetime


class TagRequest(BaseModel):
    tag: str
