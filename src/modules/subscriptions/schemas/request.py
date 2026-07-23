import uuid
from typing import Literal

from pydantic import BaseModel, field_validator


class CreateSubscriptionCheckoutRequest(BaseModel):
    plan_id: uuid.UUID
    provider: Literal["momo"]
    return_url: str | None = None

    @field_validator("return_url")
    @classmethod
    def _return_url_must_be_absolute_http(cls, value: str | None) -> str | None:
        """Gets embedded as the provider's post-payment redirect target — must
        be an absolute http(s) URL, not an open redirect to an arbitrary scheme."""
        if value is not None and not (value.startswith("http://") or value.startswith("https://")):
            raise ValueError("return_url must be an absolute http:// or https:// URL")
        return value
