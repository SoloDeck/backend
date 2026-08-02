import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TermTemplateOption(BaseModel):
    """Một lựa chọn mẫu điều khoản cho freelancer (chỉ id + tên, đủ để dựng danh sách)."""

    id: uuid.UUID
    name: str


class PublicProposalResponse(BaseModel):
    """Client-facing read-only view via share link — no internal IDs exposed."""

    model_config = ConfigDict(from_attributes=True)

    version_number: int
    status: str
    content: dict
    sent_at: datetime | None
    responded_at: datetime | None


class ProposalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    deal_id: uuid.UUID
    owner_user_id: uuid.UUID
    version_number: int
    status: str
    content: dict
    ai_generated: bool
    share_token: str | None
    share_expires_at: datetime | None
    sent_at: datetime | None
    responded_at: datetime | None
    created_at: datetime
    updated_at: datetime
