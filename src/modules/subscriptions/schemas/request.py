import uuid
from typing import Literal

from pydantic import BaseModel


class CreateSubscriptionCheckoutRequest(BaseModel):
    plan_id: uuid.UUID
    provider: Literal["momo"]
    return_url: str | None = None
