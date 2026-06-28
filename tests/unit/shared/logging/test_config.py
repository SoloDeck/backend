"""Tests for environment-aware log level / format resolution."""

import logging

from src.shared.logging.config import (
    resolve_log_format,
    resolve_log_level,
    resolve_log_request_body,
)


class TestResolveLogLevel:
    def test_development_defaults_to_debug(self) -> None:
        assert resolve_log_level("development", override=None) == logging.DEBUG

    def test_staging_defaults_to_info(self) -> None:
        assert resolve_log_level("staging", override=None) == logging.INFO

    def test_production_defaults_to_info(self) -> None:
        assert resolve_log_level("production", override=None) == logging.INFO

    def test_env_override_wins(self) -> None:
        assert resolve_log_level("development", override="WARNING") == logging.WARNING

    def test_override_is_case_insensitive(self) -> None:
        assert resolve_log_level("development", override="error") == logging.ERROR

    def test_invalid_override_falls_back_to_env_default(self) -> None:
        assert resolve_log_level("staging", override="LOUD") == logging.INFO

    def test_production_never_allows_debug_even_with_override(self) -> None:
        assert resolve_log_level("production", override="DEBUG") == logging.INFO


class TestResolveLogFormat:
    def test_development_defaults_to_console(self) -> None:
        assert resolve_log_format("development", override=None) == "console"

    def test_staging_defaults_to_json(self) -> None:
        assert resolve_log_format("staging", override=None) == "json"

    def test_production_defaults_to_json(self) -> None:
        assert resolve_log_format("production", override=None) == "json"

    def test_override_wins(self) -> None:
        assert resolve_log_format("development", override="json") == "json"

    def test_invalid_override_falls_back(self) -> None:
        assert resolve_log_format("staging", override="xml") == "json"


class TestResolveLogRequestBody:
    def test_off_by_default(self) -> None:
        assert resolve_log_request_body("development", flag=False) is False

    def test_can_enable_outside_production(self) -> None:
        assert resolve_log_request_body("development", flag=True) is True

    def test_forced_off_in_production(self) -> None:
        assert resolve_log_request_body("production", flag=True) is False
