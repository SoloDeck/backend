import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class CreateContractRequest(BaseModel):
    """deal_id and client_id are deliberately NOT accepted here — they're derived
    from proposal_id (deal_id from the proposal, client_id from that deal), never
    trusted from the caller. Previously this schema required all three separately
    with no cross-check, so a caller could pass a proposal_id from one deal
    alongside a deal_id/client_id from an entirely different one and the contract
    would silently persist the mismatched combination."""

    proposal_id: uuid.UUID
    content: dict = Field(default_factory=dict)
    effective_date: date | None = None
    end_date: date | None = None


class UpdateContractRequest(BaseModel):
    content: dict | None = None
    effective_date: date | None = None
    end_date: date | None = None


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
