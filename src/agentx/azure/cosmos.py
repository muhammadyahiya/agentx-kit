"""Azure Cosmos DB (NoSQL API) wrapper with structured logging and retries.

``CosmosService`` resolves auth in a fixed priority order so callers can hand
it whatever they have on hand — a connection string for local dev, an
endpoint + key for simple prod setups, or an endpoint + Managed Identity /
AAD credential for the recommended production path:

  1. explicit ``connection_string`` argument
  2. ``settings.cosmos_connection_string``
  3. ``endpoint`` (arg or settings) + ``key`` (arg or settings) — key auth
  4. ``endpoint`` (arg or settings) + ``credential`` (arg or
     ``get_default_credential(settings)``) — Managed Identity / AAD auth

If none of these resolve to usable credentials, construction fails fast with
``AzureCredentialError`` rather than deferring the failure to the first
network call.

The ``azure-cosmos`` SDK is imported lazily inside ``__init__`` so importing
``agentx.azure.cosmos`` never requires the ``azure-cosmos`` extra unless a
``CosmosService`` is actually constructed.
"""
from __future__ import annotations

from typing import Any

from ._logging import log_operation
from ._retry import retry_kwargs
from .config import AzureSettings, get_azure_settings
from .credentials import AzureCredentialError, get_default_credential


class CosmosService:
    """Thin, opinionated wrapper around the Cosmos DB NoSQL API client.

    Ensures the target database/container exist on construction, then
    exposes CRUD-ish helpers (``upsert``, ``get``, ``query``, ``delete``)
    that are each individually logged via ``log_operation("cosmos")``.
    """

    def __init__(
        self,
        database: str,
        container: str = "items",
        partition_key: str = "/id",
        connection_string: str | None = None,
        endpoint: str | None = None,
        key: str | None = None,
        credential: Any = None,
        settings: AzureSettings | None = None,
    ) -> None:
        try:
            from azure.cosmos import CosmosClient, PartitionKey, exceptions
        except ImportError as exc:
            raise RuntimeError(
                "azure-cosmos is not installed. Run "
                "`pip install 'agentx-kit[azure-cosmos]'`."
            ) from exc

        self._exceptions = exceptions
        self._partition_key_path = partition_key

        settings = settings or get_azure_settings()
        cs = connection_string or settings.cosmos_connection_string
        endpoint = endpoint or settings.cosmos_endpoint
        key = key or settings.cosmos_key

        if cs:
            client = CosmosClient.from_connection_string(cs, **retry_kwargs(settings))
        elif endpoint and key:
            client = CosmosClient(url=endpoint, credential=key, **retry_kwargs(settings))
        elif endpoint:
            aad_credential = credential or get_default_credential(settings)
            client = CosmosClient(url=endpoint, credential=aad_credential, **retry_kwargs(settings))
        else:
            raise AzureCredentialError(
                "CosmosService has no usable credentials: provide a connection_string, "
                "an endpoint+key, or an endpoint with Managed Identity/AAD available "
                "(directly, or via AzureSettings / AZURE_COSMOS_* env vars)."
            )

        self._db = client.create_database_if_not_exists(database)
        self._container = self._db.create_container_if_not_exists(
            id=container, partition_key=PartitionKey(path=partition_key)
        )

    @log_operation("cosmos")
    def upsert(self, item: dict) -> dict:
        """Insert or replace ``item`` (matched by its ``id`` + partition key)."""
        return self._container.upsert_item(item)

    @log_operation("cosmos")
    def get(self, id: str, partition_key: str | None = None) -> dict | None:
        """Read a single item by id, or ``None`` if it doesn't exist.

        Defaults ``partition_key`` to ``id`` to match the ``partition_key="/id"``
        convention used by ``__init__``.
        """
        pk = partition_key if partition_key is not None else id
        try:
            return self._container.read_item(item=id, partition_key=pk)
        except self._exceptions.CosmosResourceNotFoundError:
            return None

    @log_operation("cosmos")
    def query(
        self,
        query: str,
        parameters: list[dict] | None = None,
        enable_cross_partition: bool = True,
    ) -> list[dict]:
        """Run a SQL query and return all matching items as a list."""
        return list(
            self._container.query_items(
                query=query,
                parameters=parameters,
                enable_cross_partition_query=enable_cross_partition,
            )
        )

    @log_operation("cosmos")
    def delete(self, id: str, partition_key: str | None = None) -> None:
        """Delete an item by id. Already-deleted items are not an error."""
        pk = partition_key if partition_key is not None else id
        try:
            self._container.delete_item(item=id, partition_key=pk)
        except self._exceptions.CosmosResourceNotFoundError:
            pass
