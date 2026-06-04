import uuid

from pydantic import BaseModel


class ProposalRequest(BaseModel):
    deal_id: uuid.UUID
    content: dict
    status: str = "draft"
