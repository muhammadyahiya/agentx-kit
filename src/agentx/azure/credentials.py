"""Shared Azure credential resolution.

Managed Identity / Azure AD is the recommended path in production (no secrets
to leak, rotate, or store); connection strings remain a supported escape
hatch for local dev or services where AAD data-plane roles aren't set up yet.
"""
from __future__ import annotations

from typing import Any

from .config import AzureSettings, get_azure_settings


class AzureCredentialError(RuntimeError):
    """Raised when a wrapper has no usable credential or connection info."""


def get_default_credential(settings: AzureSettings | None = None) -> Any:
    """Return a ``DefaultAzureCredential`` (Managed Identity chain, then AAD dev fallbacks).

    Lazy-imports ``azure-identity`` — install any ``agentx-kit[azure-*]`` extra
    (they all depend on it) to use ``agentx.azure``.
    """
    try:
        from azure.identity import DefaultAzureCredential
    except ImportError as exc:  # pragma: no cover - exercised via importorskip in tests
        raise AzureCredentialError(
            "azure-identity is not installed. Run "
            "`pip install 'agentx-kit[azure-platform]'` (or a specific azure-* extra) "
            "to use agentx.azure."
        ) from exc

    settings = settings or get_azure_settings()
    kwargs: dict[str, Any] = {}
    if settings.client_id:
        kwargs["managed_identity_client_id"] = settings.client_id
    return DefaultAzureCredential(**kwargs)
