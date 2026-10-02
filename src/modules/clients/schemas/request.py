from datetime import datetime

from pydantic import BaseModel, Field

from src.modules.clients.domain.value_objects.client_status import (
    ClientStatus,
    ClientType,
    CommChannel,
)
from src.shared.types.length_limits import LengthLimitedModel


# Mọi `max_length` dưới đây ĐÚNG BẰNG độ dài cột trong `ClientModel` (`models.py`) — test
# `test_request_length_limits.py` canh chỗ lệch. Trước đây chỉ `name` có giới hạn: email, số điện
# thoại, thành phố, quốc gia dài hơn cột là Postgres từ chối bằng StringDataRightTruncationError
# và API trả 500 thay vì 422. `website`/`linkedin_url`/`notes`/`description` là cột TEXT nên
# không có giới hạn để khớp.  #Huynh
class ClientRequest(LengthLimitedModel):
    name: str = Field(min_length=1, max_length=255, title="Tên khách hàng")
    email: str | None = Field(default=None, max_length=255, title="Email")
    phone: str | None = Field(default=None, max_length=50, title="Số điện thoại")
    type: ClientType = ClientType.INDIVIDUAL
    website: str | None = None
    linkedin_url: str | None = None
    address_city: str | None = Field(default=None, max_length=100, title="Thành phố")
    address_country: str | None = Field(default=None, max_length=100, title="Quốc gia")
    status: ClientStatus = ClientStatus.PROSPECT
    notes: str | None = None
    description: str | None = None


class ClientUpdateRequest(LengthLimitedModel):
    """Partial update — every field is optional and omitted fields are left untouched.

    Distinct from ClientRequest (create): that schema's `type`/`status` defaults
    ("individual"/"prospect") are correct for a new client, but the same defaults
    on a PATCH body silently reset an existing client's real type/status back to
    them whenever the caller omits those fields — this schema's None defaults are
    what let the service layer's `if value is not None` skip actually work.
    """

    name: str | None = Field(default=None, min_length=1, max_length=255, title="Tên khách hàng")
    email: str | None = Field(default=None, max_length=255, title="Email")
    phone: str | None = Field(default=None, max_length=50, title="Số điện thoại")
    type: ClientType | None = None
    website: str | None = None
    linkedin_url: str | None = None
    address_city: str | None = Field(default=None, max_length=100, title="Thành phố")
    address_country: str | None = Field(default=None, max_length=100, title="Quốc gia")
    status: ClientStatus | None = None
    notes: str | None = None
    description: str | None = None


class CommLogRequest(BaseModel):
    channel: CommChannel
    summary: str
    communicated_at: datetime


class TagRequest(BaseModel):
    tag: str
