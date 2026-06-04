import uuid

from pydantic import BaseModel


class ContractRequest(BaseModel):
    deal_id: uuid.UUID
    proposal_id: uuid.UUID
    client_id: uuid.UUID
    content: dict
