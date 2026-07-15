"""Mock-based unit tests for agentx.azure.monitor — no live Azure calls."""
from __future__ import annotations

from unittest import mock

import pytest

pytest.importorskip("azure.monitor.opentelemetry")

import agentx.azure.monitor as monitor_mod  # noqa: E402
from agentx.azure.config import reset_azure_settings  # noqa: E402


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv("APPLICATIONINSIGHTS_CONNECTION_STRING", raising=False)
    monkeypatch.delenv("AGENTX_TELEMETRY", raising=False)
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    reset_azure_settings()
    monitor_mod._CONFIGURED = False
    yield
    reset_azure_settings()
    monitor_mod._CONFIGURED = False


def test_no_connection_string_is_noop():
    assert monitor_mod.setup_azure_monitor() is False


def test_telemetry_disabled_is_noop(monkeypatch):
    monkeypatch.setenv("AGENTX_TELEMETRY", "false")
    assert monitor_mod.setup_azure_monitor(connection_string="InstrumentationKey=abc") is False


def test_configures_azure_monitor_when_connection_string_present():
    with mock.patch("azure.monitor.opentelemetry.configure_azure_monitor") as mock_configure:
        result = monitor_mod.setup_azure_monitor(connection_string="InstrumentationKey=abc", service_name="my-svc")

        assert result is True
        mock_configure.assert_called_once()
        _, kwargs = mock_configure.call_args
        assert kwargs["connection_string"] == "InstrumentationKey=abc"
        assert kwargs["resource_attributes"] == {"service.name": "my-svc"}


def test_second_call_is_idempotent_noop():
    with mock.patch("azure.monitor.opentelemetry.configure_azure_monitor") as mock_configure:
        monitor_mod.setup_azure_monitor(connection_string="InstrumentationKey=abc")
        monitor_mod.setup_azure_monitor(connection_string="InstrumentationKey=abc")
        mock_configure.assert_called_once()


def test_configure_exception_is_caught_and_returns_false():
    with mock.patch("azure.monitor.opentelemetry.configure_azure_monitor", side_effect=RuntimeError("boom")):
        assert monitor_mod.setup_azure_monitor(connection_string="InstrumentationKey=abc") is False


def test_emit_metric_logs_when_not_configured(caplog):
    import logging

    with caplog.at_level(logging.INFO, logger="agentx.azure.monitor"):
        monitor_mod.emit_metric("jobs_processed", 3, queue="invoice")
    assert any("jobs_processed" in r.message for r in caplog.records)
