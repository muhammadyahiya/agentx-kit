"""Azure Key Vault wrapper — Managed Identity only, with a short-lived read cache.

Key Vault has no connection-string escape hatch in this design (unlike blob
storage or Cosmos): every secret read/write goes through AAD, via an explicit
``credential`` argument or ``get_default_credential(settings)``
(``DefaultAzureCredential`` — Managed Identity in prod, developer credentials
locally). ``vault_url`` (argument or ``settings.keyvault_url``) is the only
other required input.

Key Vault also enforces fairly low per-vault rate limits, and secrets are
frequently re-read on every request in a hot path (e.g. a DB password fetched
per pipeline run). A small in-process TTL cache — keyed by secret name,
storing ``(value, expiry)`` using ``time.monotonic()`` — avoids hammering the
vault for values that rarely change, while ``invalidate_cache()`` and
``set_secret()`` keep it from serving stale data after a known write.

Every public method is wrapped in ``@log_operation("keyvault")`` so calls
emit structured start/success/failure log lines (with ``correlation_id``,
``duration_ms``) via ``agentx.azure._logging`` — no bespoke logging here.
"""
from __future__ import annotations

import time
from typing import Any

from ._logging import log_operation
from ._retry import retry_kwargs
from .config import AzureSettings, get_azure_settings
from .credentials import AzureCredentialError, get_default_credential


class KeyVaultService:
    """Thin, typed wrapper around ``azure.keyvault.secrets.SecretClient``.

    Resolves auth in this order:
      1. ``vault_url`` argument, else ``settings.keyvault_url``
         (``AZURE_KEYVAULT_URL``) — raises ``AzureCredentialError`` if neither
         is set.
      2. ``credential`` argument, else ``get_default_credential(settings)``
         — always AAD, there is no connection-string mode for Key Vault here.

    Reads are cached in-process for ``cache_ttl_seconds`` (default 300s) to
    avoid re-hitting Key Vault's low rate limits from a hot path.
    """

    def __init__(
        self,
        vault_url: str | None = None,
        credential: Any = None,
        settings: AzureSettings | None = None,
        cache_ttl_seconds: float = 300.0,
    ) -> None:
        try:
            from azure.keyvault.secrets import SecretClient
        except ImportError as exc:
            raise RuntimeError(
                "azure-keyvault-secrets is not installed. Run "
                "`pip install 'agentx-kit[azure-keyvault]'`."
            ) from exc

        settings = settings or get_azure_settings()

        resolved_vault_url = vault_url or settings.keyvault_url
        if not resolved_vault_url:
            raise AzureCredentialError(
                "Key Vault URL not configured — pass vault_url or set AZURE_KEYVAULT_URL"
            )

        resolved_credential = credential or get_default_credential(settings)

        self._cache_ttl_seconds = cache_ttl_seconds
        self._cache: dict[str, tuple[str, float]] = {}
        self._client = SecretClient(
            vault_url=resolved_vault_url,
            credential=resolved_credential,
            **retry_kwargs(settings),
        )

    @log_operation("keyvault")
    def get_secret(self, name: str, use_cache: bool = True) -> str:
        """Return the current value of secret ``name``.

        Serves a cached value (if fresh) when ``use_cache`` is ``True``;
        otherwise always fetches from Key Vault and refreshes the cache.
        """
        if use_cache:
            cached = self._cache.get(name)
            if cached is not None:
                value, expiry = cached
                if time.monotonic() < expiry:
                    return value

        value = self._client.get_secret(name).value
        self._cache[name] = (value, time.monotonic() + self._cache_ttl_seconds)
        return value

    @log_operation("keyvault")
    def set_secret(self, name: str, value: str) -> None:
        """Create or update secret ``name`` and refresh its cache entry."""
        self._client.set_secret(name, value)
        self._cache[name] = (value, time.monotonic() + self._cache_ttl_seconds)

    @log_operation("keyvault")
    def invalidate_cache(self, name: str | None = None) -> None:
        """Drop the cached value for ``name``, or clear the whole cache if omitted."""
        if name is None:
            self._cache.clear()
        else:
            self._cache.pop(name, None)
