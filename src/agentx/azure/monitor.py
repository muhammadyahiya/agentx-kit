"""Azure Monitor / Application Insights: OpenTelemetry export for agentx.azure.

Follows the same convention as ``agentx.observability`` (which wires LangChain
spans to a generic OTel/Langfuse backend): lazy, optional, honours the same
``AGENTX_TELEMETRY`` / ``OTEL_SDK_DISABLED`` kill switch, and never crashes an
app if the extra isn't installed or no connection string is configured. This
module is the Azure-specific *exporter* — ``agentx.observability.setup_tracing``
remains the generic one; call both if you want LangChain spans AND Azure
service-wrapper spans in the same Application Insights resource.
"""
from __future__ import annotations

from typing import Any

from ..observability import telemetry_enabled
from ._logging import azure_logger
from .config import AzureSettings, get_azure_settings

logger = azure_logger("monitor")

_CONFIGURED = False


def setup_azure_monitor(
    connection_string: str | None = None,
    service_name: str = "agentx",
    settings: AzureSettings | None = None,
) -> bool:
    """Instrument this process to export traces/logs/metrics to Application Insights.

    Returns ``False`` (no-op) if telemetry is disabled, no connection string is
    configured, or the ``azure-monitor-opentelemetry`` extra isn't installed —
    matching ``agentx.observability.setup_tracing``'s graceful-degrade contract.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return True
    if not telemetry_enabled():
        logger.info("Telemetry disabled; skipping Azure Monitor setup.")
        return False

    settings = settings or get_azure_settings()
    conn_str = connection_string or settings.appinsights_connection_string
    if not conn_str:
        logger.info(
            "No Application Insights connection string configured "
            "(pass connection_string or set APPLICATIONINSIGHTS_CONNECTION_STRING)."
        )
        return False

    try:
        from azure.monitor.opentelemetry import configure_azure_monitor
    except ImportError:
        logger.info(
            "azure-monitor-opentelemetry not installed; run "
            "`pip install 'agentx-kit[azure-monitor]'`."
        )
        return False

    try:
        configure_azure_monitor(connection_string=conn_str, resource_attributes={"service.name": service_name})
        _CONFIGURED = True
        logger.info("Azure Monitor OpenTelemetry export enabled for '%s'.", service_name)
        return True
    except Exception as exc:  # noqa: BLE001 - telemetry setup must never crash the app
        logger.warning("Azure Monitor setup failed: %s", exc)
        return False


def emit_metric(name: str, value: float, **dimensions: Any) -> None:
    """Record a custom metric via the active OTel meter if configured, else just log it.

    Best-effort: if Azure Monitor hasn't been set up (or the OTel API isn't
    installed), the metric is still visible as a structured log line rather
    than silently dropped.
    """
    if _CONFIGURED:
        try:
            from opentelemetry import metrics

            meter = metrics.get_meter("agentx.azure")
            meter.create_gauge(name).set(value, attributes=dimensions)
            return
        except Exception as exc:  # noqa: BLE001 - fall back to logging below
            logger.debug("emit_metric via OTel failed, falling back to log: %s", exc)
    logger.info("metric %s=%s %s", name, value, dimensions, extra={"service": "monitor", "metric": name, **dimensions})
