"""Azure platform configuration (pydantic-settings).

Two auth modes, resolved per-wrapper (Managed Identity preferred):
  * Managed Identity / Azure AD — ``DefaultAzureCredential`` (recommended, prod).
  * Connection strings / keys — per-service env vars (local dev, or services
    without an AAD data-plane role, e.g. Cosmos key auth).

Only generic, cross-service knobs live here; each wrapper stays azure-sdk-free
at import time until its ``agentx-kit[azure-*]`` extra is installed.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AzureSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # ---- identity ----
    client_id: str | None = Field(
        default=None, alias="AZURE_CLIENT_ID",
        description="User-assigned managed identity client ID (omit for system-assigned).",
    )

    # ---- blob storage ----
    storage_connection_string: str | None = Field(default=None, alias="AZURE_STORAGE_CONNECTION_STRING")
    storage_account_url: str | None = Field(default=None, alias="AZURE_STORAGE_ACCOUNT_URL")

    # ---- service bus ----
    servicebus_connection_string: str | None = Field(default=None, alias="AZURE_SERVICEBUS_CONNECTION_STRING")
    servicebus_namespace: str | None = Field(
        default=None, alias="AZURE_SERVICEBUS_NAMESPACE",
        description="<namespace>.servicebus.windows.net, used with Managed Identity.",
    )

    # ---- cosmos db ----
    cosmos_connection_string: str | None = Field(default=None, alias="AZURE_COSMOS_CONNECTION_STRING")
    cosmos_endpoint: str | None = Field(default=None, alias="AZURE_COSMOS_ENDPOINT")
    cosmos_key: str | None = Field(default=None, alias="AZURE_COSMOS_KEY")

    # ---- key vault ----
    keyvault_url: str | None = Field(default=None, alias="AZURE_KEYVAULT_URL")

    # ---- event grid ----
    eventgrid_topic_endpoint: str | None = Field(default=None, alias="AZURE_EVENTGRID_TOPIC_ENDPOINT")
    eventgrid_topic_key: str | None = Field(default=None, alias="AZURE_EVENTGRID_TOPIC_KEY")

    # ---- monitor / app insights ----
    appinsights_connection_string: str | None = Field(default=None, alias="APPLICATIONINSIGHTS_CONNECTION_STRING")

    # ---- resource manager (container apps, ml workspace, ...) ----
    subscription_id: str | None = Field(default=None, alias="AZURE_SUBSCRIPTION_ID")
    resource_group: str | None = Field(default=None, alias="AZURE_RESOURCE_GROUP")
    location: str = Field(default="eastus", alias="AZURE_LOCATION")

    # ---- azure ml ----
    ml_workspace_name: str | None = Field(default=None, alias="AZURE_ML_WORKSPACE_NAME")

    # ---- retry defaults (shared across every wrapper's azure-core client) ----
    retry_total: int = Field(default=5, alias="AGENTX_AZURE_RETRY_TOTAL", ge=0)
    retry_backoff_seconds: float = Field(default=0.8, alias="AGENTX_AZURE_RETRY_BACKOFF", ge=0.0)


@lru_cache
def get_azure_settings() -> AzureSettings:
    return AzureSettings()


def reset_azure_settings() -> None:
    """Clear the ``get_azure_settings()`` cache — re-reads env/.env on next call.

    Tests that mutate Azure env vars between cases should call this.
    """
    get_azure_settings.cache_clear()
