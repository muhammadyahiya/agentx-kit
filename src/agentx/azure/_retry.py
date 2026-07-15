"""Shared retry tuning for azure-core-based clients.

Every azure-sdk-for-python client accepts ``retry_total`` / ``retry_backoff_factor``
(consumed by its azure-core pipeline's ``RetryPolicy``) as constructor kwargs.
Centralizing them here means retry behaviour is tuned once, via env vars
(``AGENTX_AZURE_RETRY_TOTAL`` / ``AGENTX_AZURE_RETRY_BACKOFF``), instead of each
wrapper hand-rolling its own.
"""
from __future__ import annotations

from typing import Any

from .config import AzureSettings, get_azure_settings


def retry_kwargs(settings: AzureSettings | None = None) -> dict[str, Any]:
    """Return ``{"retry_total": ..., "retry_backoff_factor": ...}`` for client construction."""
    settings = settings or get_azure_settings()
    return {
        "retry_total": settings.retry_total,
        "retry_backoff_factor": settings.retry_backoff_seconds,
    }
