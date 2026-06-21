import uuid

from pydantic import BaseModel, Field


class ContractRequest(BaseModel):
    deal_id: uuid.UUID
    proposal_id: uuid.UUID
    client_id: uuid.UUID
    content: dict


class ContractStatusRequest(BaseModel):
    status: str = Field(
        ...,
        description=(
            "Target status. Valid transitions: "
            "draft→pending_signatures, "
            "pending_signatures→active|expired, "
            "active→completed|terminated"
        ),
    )


class ContractTerminateRequest(BaseModel):
    reason: str | None = Field(default=None, description="Optional termination reason")
