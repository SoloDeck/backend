"""Tích hợp Zalo Official Account (client thật + mock, PKCE, chữ ký webhook)."""

from src.integrations.zalo.client import (
    MockZaloOAClient,
    RealZaloOAClient,
    ZaloError,
    ZaloOAClient,
    ZaloPermanentError,
    ZaloToken,
    ZaloTransientError,
    code_challenge_for,
    generate_code_verifier,
    get_zalo_client,
    verify_zalo_signature,
)

__all__ = [
    "MockZaloOAClient",
    "RealZaloOAClient",
    "ZaloError",
    "ZaloOAClient",
    "ZaloPermanentError",
    "ZaloToken",
    "ZaloTransientError",
    "code_challenge_for",
    "generate_code_verifier",
    "get_zalo_client",
    "verify_zalo_signature",
]
