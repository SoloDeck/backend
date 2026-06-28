"""Tests for sensitive-data redaction in logging."""

from src.shared.logging.redaction import REDACTED, redact_mapping, redact_processor


class TestRedactMapping:
    def test_redacts_password_field(self) -> None:
        assert redact_mapping({"password": "hunter2"}) == {"password": REDACTED}

    def test_redacts_token_variants(self) -> None:
        out = redact_mapping(
            {"token": "x", "refresh_token": "y", "access_token": "z"}
        )
        assert out == {
            "token": REDACTED,
            "refresh_token": REDACTED,
            "access_token": REDACTED,
        }

    def test_redacts_authorization_and_cookie_headers(self) -> None:
        out = redact_mapping({"Authorization": "Bearer abc", "Cookie": "sid=1"})
        assert out == {"Authorization": REDACTED, "Cookie": REDACTED}

    def test_redacts_secret_substring_case_insensitive(self) -> None:
        out = redact_mapping({"Client_Secret": "s", "MY_SECRET": "v"})
        assert out == {"Client_Secret": REDACTED, "MY_SECRET": REDACTED}

    def test_redacts_otp_cvv_card(self) -> None:
        out = redact_mapping(
            {"otp": "123456", "cvv": "999", "credit_card": "4111111111111111"}
        )
        assert out == {"otp": REDACTED, "cvv": REDACTED, "credit_card": REDACTED}

    def test_does_not_redact_benign_fields(self) -> None:
        data = {
            "username": "alice",
            "user_id": "u-1",
            "email": "a@b.com",
            "status_code": 200,
            "duration_ms": 12.5,
        }
        assert redact_mapping(data) == data

    def test_redacts_nested_dict(self) -> None:
        out = redact_mapping({"user": {"name": "a", "password": "p"}})
        assert out == {"user": {"name": "a", "password": REDACTED}}

    def test_redacts_inside_list_of_dicts(self) -> None:
        out = redact_mapping({"items": [{"token": "t"}, {"ok": 1}]})
        assert out == {"items": [{"token": REDACTED}, {"ok": 1}]}

    def test_does_not_mutate_input(self) -> None:
        src = {"password": "p"}
        redact_mapping(src)
        assert src == {"password": "p"}


class TestRedactProcessor:
    def test_processor_redacts_event_dict(self) -> None:
        event = {"event": "login", "password": "p", "user_id": "u1"}
        out = redact_processor(None, "info", event)
        assert out == {"event": "login", "password": REDACTED, "user_id": "u1"}
