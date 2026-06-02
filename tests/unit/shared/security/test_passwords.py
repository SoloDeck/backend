import pytest

from src.shared.security.passwords import hash_password, verify_password


def test_hash_password_returns_string():
    result = hash_password("secret")
    assert isinstance(result, str)
    assert len(result) > 0


def test_hash_password_is_not_plaintext():
    plain = "my_password_123"
    assert hash_password(plain) != plain


def test_hash_password_produces_unique_hashes():
    plain = "same_password"
    assert hash_password(plain) != hash_password(plain)


def test_verify_password_correct():
    plain = "correct_horse_battery_staple"
    hashed = hash_password(plain)
    assert verify_password(plain, hashed) is True


def test_verify_password_wrong():
    hashed = hash_password("correct")
    assert verify_password("wrong", hashed) is False


def test_verify_password_empty_against_hash():
    hashed = hash_password("notempty")
    assert verify_password("", hashed) is False
