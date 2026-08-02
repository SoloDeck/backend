import uuid
from datetime import date
from decimal import Decimal

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


class ClientSignRequest(BaseModel):
    """Client's signature, submitted via the public share link."""

    signer_name: str = Field(..., description="Name of the client signatory")


class CreatePaymentMilestoneRequest(BaseModel):
    description: str
    amount: Decimal = Field(gt=0)
    due_date: date | None = None
    sort_order: int = 0


class UpdatePaymentMilestoneRequest(BaseModel):
    description: str | None = None
    amount: Decimal | None = Field(default=None, gt=0)
    due_date: date | None = None
    sort_order: int | None = None
