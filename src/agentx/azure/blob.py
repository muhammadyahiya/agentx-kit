"""Azure Blob Storage wrapper — Managed Identity first, connection string fallback.

Production usage should rely on Managed Identity: pass no credentials at all
and let ``account_url`` (or ``AZURE_STORAGE_ACCOUNT_URL``) plus
``get_default_credential()`` (``DefaultAzureCredential``) authenticate the
``BlobServiceClient``. Connection strings remain a supported escape hatch for
local dev or environments without an AAD data-plane role assigned yet — an
explicit ``connection_string`` argument or ``AZURE_STORAGE_CONNECTION_STRING``
always wins when present, since that's the more specific configuration.

Every public method is wrapped in ``@log_operation("blob")`` so calls emit
structured start/success/failure log lines (with ``correlation_id``,
``duration_ms``) via ``agentx.azure._logging`` — no bespoke logging here.
"""
from __future__ import annotations

from typing import Any

from ._logging import log_operation
from ._retry import retry_kwargs
from .config import AzureSettings, get_azure_settings
from .credentials import AzureCredentialError, get_default_credential


class BlobStorageService:
    """Thin, typed wrapper around ``azure.storage.blob.BlobServiceClient``.

    Resolves auth in this order:
      1. Explicit ``connection_string`` argument.
      2. ``settings.storage_connection_string`` (``AZURE_STORAGE_CONNECTION_STRING``).
      3. ``account_url`` (argument or ``settings.storage_account_url``) combined
         with ``credential`` (argument or ``get_default_credential(settings)``)
         — the Managed Identity path.

    Raises ``AzureCredentialError`` if none of the above yields enough
    information to build a client.
    """

    def __init__(
        self,
        container: str,
        connection_string: str | None = None,
        account_url: str | None = None,
        credential: Any = None,
        settings: AzureSettings | None = None,
    ) -> None:
        try:
            from azure.storage.blob import BlobServiceClient, ContentSettings
        except ImportError as exc:
            raise RuntimeError(
                "azure-storage-blob is not installed. Run "
                "`pip install 'agentx-kit[azure-blob]'`."
            ) from exc

        self._content_settings_cls = ContentSettings
        settings = settings or get_azure_settings()

        conn_str = connection_string or settings.storage_connection_string
        resolved_account_url = account_url or settings.storage_account_url

        if conn_str:
            client = BlobServiceClient.from_connection_string(conn_str, **retry_kwargs(settings))
        elif resolved_account_url:
            resolved_credential = credential or get_default_credential(settings)
            client = BlobServiceClient(
                account_url=resolved_account_url,
                credential=resolved_credential,
                **retry_kwargs(settings),
            )
        else:
            raise AzureCredentialError(
                "BlobStorageService needs either a connection string "
                "(connection_string arg or AZURE_STORAGE_CONNECTION_STRING) or "
                "an account URL (account_url arg or AZURE_STORAGE_ACCOUNT_URL) "
                "plus a credential for Managed Identity."
            )

        self._container_client = client.get_container_client(container)
        self._ensure_container()

    def _ensure_container(self) -> None:
        from azure.core.exceptions import ResourceExistsError

        try:
            self._container_client.create_container()
        except ResourceExistsError:
            pass

    @log_operation("blob")
    def upload(
        self,
        name: str,
        data: bytes,
        overwrite: bool = True,
        content_type: str | None = None,
    ) -> str:
        """Upload ``data`` as blob ``name``, returning the resulting blob URL."""
        kwargs: dict[str, Any] = {"overwrite": overwrite}
        if content_type:
            kwargs["content_settings"] = self._content_settings_cls(content_type=content_type)
        blob_client = self._container_client.upload_blob(name, data, **kwargs)
        return blob_client.url

    @log_operation("blob")
    def download(self, name: str) -> bytes:
        """Download blob ``name`` and return its full contents as bytes."""
        return self._container_client.download_blob(name).readall()

    @log_operation("blob")
    def list_blobs(self, prefix: str | None = None) -> list[str]:
        """Return the names of blobs in the container, optionally filtered by prefix."""
        return [b.name for b in self._container_client.list_blobs(name_starts_with=prefix)]

    @log_operation("blob")
    def delete(self, name: str) -> None:
        """Delete blob ``name``."""
        self._container_client.delete_blob(name)

    @log_operation("blob")
    def exists(self, name: str) -> bool:
        """Return whether blob ``name`` exists in the container."""
        return self._container_client.get_blob_client(name).exists()
