import uuid

import pytest
from pydantic import ValidationError

from src.modules.subscriptions.schemas.request import CreateSubscriptionCheckoutRequest


def _payload(return_url):
    return {"plan_id": str(uuid.uuid4()), "provider": "momo", "return_url": return_url}


def test_accepts_https_return_url() -> None:
    req = CreateSubscriptionCheckoutRequest(**_payload("https://app.solodesk.space/billing/result"))
    assert req.return_url == "https://app.solodesk.space/billing/result"


def test_accepts_registered_deep_link() -> None:
    req = CreateSubscriptionCheckoutRequest(**_payload("solodesk://payment-result"))
    assert req.return_url == "solodesk://payment-result"


def test_accepts_none() -> None:
    req = CreateSubscriptionCheckoutRequest(**_payload(None))
    assert req.return_url is None


@pytest.mark.parametrize(
    "bad_url",
    [
        "solodesk://payment-result/evil",
        "solodesk://other",
        "javascript:alert(1)",
        "ftp://x",
    ],
)
def test_rejects_unregistered_or_unsafe_return_url(bad_url: str) -> None:
    with pytest.raises(ValidationError):
        CreateSubscriptionCheckoutRequest(**_payload(bad_url))
