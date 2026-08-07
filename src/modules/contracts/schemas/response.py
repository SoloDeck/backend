import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class TermTemplateOption(BaseModel):
    """Một lựa chọn mẫu điều khoản cho freelancer (chỉ id + tên, đủ để dựng danh sách)."""

    id: uuid.UUID
    name: str


class PublicContractResponse(BaseModel):
    """Client-facing read-only view via share link — only what's needed to review and sign."""

    model_config = ConfigDict(from_attributes=True)

    version_number: int
    status: str
    content: dict
    effective_date: date | None
    end_date: date | None
    signed_by_freelancer_at: datetime | None
    signed_by_client_at: datetime | None


class ContractResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    deal_id: uuid.UUID
    proposal_id: uuid.UUID
    client_id: uuid.UUID
    owner_user_id: uuid.UUID
    version_number: int
    status: str
    content: dict
    client_snapshot: dict
    effective_date: date | None
    end_date: date | None
    signed_by_freelancer_at: datetime | None
    signed_by_client_at: datetime | None
    share_token: str | None
    created_at: datetime
    updated_at: datetime


class ContractExportResponse(BaseModel):
    status: str
    task_id: str | None = None
    download_url: str | None = None


class PaymentMilestoneResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    contract_id: uuid.UUID
    description: str
    amount: Decimal
    due_date: date | None
    invoice_id: uuid.UUID | None
    sort_order: int
    created_at: datetime
