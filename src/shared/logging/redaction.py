"""Redact sensitive fields before they reach a log sink.

A field is considered sensitive when its (lower-cased) name contains any of the
substrings in ``SENSITIVE_SUBSTRINGS``. Matching is recursive across nested
mappings and lists so that request bodies, headers, and structured error
context are masked consistently.
"""

from collections.abc import Mapping
from typing import Any

REDACTED = "***REDACTED***"

# Substring match (case-insensitive) on the field NAME. Kept deliberately
# narrow to avoid masking legitimate fields such as ``card_holder_name`` or
# ``username``. See the task summary for known edge cases (e.g. ``tokens_used``).
SENSITIVE_SUBSTRINGS: tuple[str, ...] = (
    "password",
    "passwd",
    "secret",
    "token",
    "authorization",
    "cookie",
    "otp",
    "cvv",
    "cvc",
    "credit_card",
    "card_number",
    "cardnumber",
    "api_key",
    "apikey",
    "ssn",
)


def _is_sensitive_key(key: Any) -> bool:
    if not isinstance(key, str):
        return False
    lowered = key.lower()
    return any(needle in lowered for needle in SENSITIVE_SUBSTRINGS)


def _redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {k: (REDACTED if _is_sensitive_key(k) else _redact(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        rebuilt = [_redact(item) for item in value]
        return type(value)(rebuilt) if isinstance(value, tuple) else rebuilt
    return value


def redact_mapping(data: Mapping[str, Any]) -> dict[str, Any]:
    """Return a deep copy of ``data`` with sensitive values masked."""
    return _redact(dict(data))


def redact_processor(_logger: Any, _method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """structlog processor that redacts sensitive keys in every log entry."""
    return redact_mapping(event_dict)
