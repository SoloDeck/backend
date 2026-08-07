import uuid
from typing import Literal

from pydantic import BaseModel, field_validator

# Exact-match allowlist of custom-scheme deep links the mobile app registers as
# a payment-result landing target. Exact match only — "solodesk://payment-result/x"
# or a different scheme/host must NOT pass, to avoid this becoming an open redirect.
_ALLOWED_CUSTOM_RETURN_URLS = frozenset({"solodesk://payment-result"})


class ChangePlanRequest(BaseModel):
    plan_id: uuid.UUID


class CreateSubscriptionCheckoutRequest(BaseModel):
    plan_id: uuid.UUID
    provider: Literal["momo"]
    return_url: str | None = None

    @field_validator("return_url")
    @classmethod
    def _return_url_must_be_safe(cls, value: str | None) -> str | None:
        """Gets embedded as the provider's post-payment redirect target — must be
        an absolute http(s) URL, or an exact match against the app's registered
        deep link allowlist. Not an open redirect to an arbitrary scheme/host."""
        if value is None:
            return value
        if value.startswith("http://") or value.startswith("https://"):
            return value
        if value in _ALLOWED_CUSTOM_RETURN_URLS:
            return value
        raise ValueError(
            "return_url must be an absolute http:// or https:// URL, or a "
            "registered app deep link"
        )
