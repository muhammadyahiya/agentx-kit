"""Tests for Settings + logging_config edge cases fixed in Sprint 1."""
from __future__ import annotations

import logging
import os

import pytest

from agentx.config import Settings, get_settings, reset_settings
from agentx.logging_config import get_logger, setup_logging


class TestSettingsValidation:
    """Range/type validators added in Sprint 1."""

    def test_populate_by_name_python_field_names(self) -> None:
        """T1-Bug1: after populate_by_name=True, Python field names must work."""
        s = Settings(default_provider="anthropic", temperature=0.9)
        assert s.default_provider == "anthropic"
        assert s.temperature == 0.9

    def test_alias_names_still_work(self) -> None:
        s = Settings(AGENTX_PROVIDER="groq")
        assert s.default_provider == "groq"

    def test_rejects_negative_temperature(self) -> None:
        with pytest.raises(ValueError):
            Settings(temperature=-1.0)

    def test_rejects_too_high_temperature(self) -> None:
        with pytest.raises(ValueError):
            Settings(temperature=3.0)

    def test_rejects_negative_timeout(self) -> None:
        with pytest.raises(ValueError):
            Settings(request_timeout=-5)


class TestResetSettings:
    """reset_settings() clears the lru_cache."""

    def test_reset_reads_new_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        reset_settings()
        monkeypatch.setenv("AGENTX_PROVIDER", "cohere")
        s1 = get_settings()
        assert s1.default_provider == "cohere"

        reset_settings()
        monkeypatch.setenv("AGENTX_PROVIDER", "openai")
        s2 = get_settings()
        assert s2.default_provider == "openai"


class TestGetLoggerNamespacing:
    """Namespace corner cases fixed in Sprint 1."""

    def test_empty_string_returns_root_agentx(self) -> None:
        """T1-Bug2: get_logger("") must not produce "agentx." with trailing dot."""
        logger = get_logger("")
        assert logger.name == "agentx"

    def test_simple_name_prefixed(self) -> None:
        assert get_logger("mymod").name == "agentx.mymod"

    def test_agentx_prefix_preserved(self) -> None:
        assert get_logger("agentx.rag").name == "agentx.rag"

    def test_bare_agentx_returns_root(self) -> None:
        assert get_logger("agentx").name == "agentx"

    def test_agentxfoo_does_not_escape_namespace(self) -> None:
        """T1-Bug3: 'agentxfoo' must be prefixed to 'agentx.agentxfoo', not
        passed through as an unrelated logger."""
        logger = get_logger("agentxfoo")
        assert logger.name.startswith("agentx.")


class TestSetupLoggingValidation:
    """setup_logging must reject invalid level strings."""

    def test_rejects_invalid_level(self) -> None:
        """T1-Bug7: no more silent fallback to INFO."""
        with pytest.raises(ValueError, match="Invalid log level"):
            setup_logging(level="TYPO_LEVEL", force=True)

    def test_accepts_all_valid_levels(self) -> None:
        for lvl in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            setup_logging(level=lvl, force=True)
            root = logging.getLogger("agentx")
            assert root.level == getattr(logging, lvl)

    def test_lowercase_level_accepted(self) -> None:
        setup_logging(level="debug", force=True)
        root = logging.getLogger("agentx")
        assert root.level == logging.DEBUG
