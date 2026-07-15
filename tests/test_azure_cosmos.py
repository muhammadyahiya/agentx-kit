"""Unit tests for agentx.azure.cosmos.CosmosService — mocked, no live Azure calls.

``azure.cosmos`` is imported lazily inside ``CosmosService.__init__``, so there
is no module-level name in ``agentx.azure.cosmos`` to patch; instead we patch
the real SDK class where it actually lives (``azure.cosmos.CosmosClient``).
"""
from __future__ import annotations

from unittest import mock

import pytest

pytest.importorskip("azure.cosmos")

from agentx.azure.config import reset_azure_settings  # noqa: E402
from agentx.azure.credentials import AzureCredentialError  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_azure_env(monkeypatch: pytest.MonkeyPatch):
    """Ensure no ambient AZURE_COSMOS_* env leaks between tests."""
    for key in (
        "AZURE_COSMOS_CONNECTION_STRING",
        "AZURE_COSMOS_ENDPOINT",
        "AZURE_COSMOS_KEY",
        "AZURE_CLIENT_ID",
    ):
        monkeypatch.delenv(key, raising=False)
    reset_azure_settings()
    yield
    reset_azure_settings()


def _make_mock_container() -> mock.MagicMock:
    """Build a MagicMock standing in for a constructed CosmosClient's container proxy."""
    container = mock.MagicMock()
    container.upsert_item.return_value = {"id": "1", "value": "upserted"}
    container.read_item.return_value = {"id": "1", "value": "read"}
    container.query_items.return_value = iter([{"id": "1"}, {"id": "2"}])
    return container


def _wire_mock_client(MockClient: mock.MagicMock, container: mock.MagicMock) -> mock.MagicMock:
    """Wire the from_connection_string()/create_database_if_not_exists()/create_container_if_not_exists() chain."""
    db = mock.MagicMock()
    db.create_container_if_not_exists.return_value = container
    client = mock.MagicMock()
    client.create_database_if_not_exists.return_value = db
    MockClient.from_connection_string.return_value = client
    MockClient.return_value = client
    return client


def test_construct_with_connection_string():
    with mock.patch("azure.cosmos.CosmosClient") as MockClient:
        container = _make_mock_container()
        _wire_mock_client(MockClient, container)

        from agentx.azure.cosmos import CosmosService

        svc = CosmosService(
            database="my-db",
            container="my-container",
            connection_string="AccountEndpoint=https://acct.documents.azure.com:443/;AccountKey=key;",
        )

        MockClient.from_connection_string.assert_called_once()
        assert svc._container is container


def test_upsert_get_query_delete_happy_path():
    with mock.patch("azure.cosmos.CosmosClient") as MockClient:
        container = _make_mock_container()
        _wire_mock_client(MockClient, container)

        from agentx.azure.cosmos import CosmosService

        svc = CosmosService(database="my-db", connection_string="cs")

        result = svc.upsert({"id": "1", "value": "upserted"})
        assert result == {"id": "1", "value": "upserted"}
        container.upsert_item.assert_called_once_with({"id": "1", "value": "upserted"})

        item = svc.get("1")
        assert item == {"id": "1", "value": "read"}
        container.read_item.assert_called_once_with(item="1", partition_key="1")

        items = svc.query("SELECT * FROM c")
        assert items == [{"id": "1"}, {"id": "2"}]
        container.query_items.assert_called_once_with(
            query="SELECT * FROM c", parameters=None, enable_cross_partition_query=True
        )

        svc.delete("1")
        container.delete_item.assert_called_once_with(item="1", partition_key="1")


def test_get_not_found_returns_none():
    from azure.cosmos import exceptions

    with mock.patch("azure.cosmos.CosmosClient") as MockClient:
        container = _make_mock_container()
        container.read_item.side_effect = exceptions.CosmosResourceNotFoundError(
            message="not found"
        )
        _wire_mock_client(MockClient, container)

        from agentx.azure.cosmos import CosmosService

        svc = CosmosService(database="my-db", connection_string="cs")

        assert svc.get("missing") is None


def test_delete_not_found_is_silent():
    from azure.cosmos import exceptions

    with mock.patch("azure.cosmos.CosmosClient") as MockClient:
        container = _make_mock_container()
        container.delete_item.side_effect = exceptions.CosmosResourceNotFoundError(
            message="not found"
        )
        _wire_mock_client(MockClient, container)

        from agentx.azure.cosmos import CosmosService

        svc = CosmosService(database="my-db", connection_string="cs")

        # Should not raise despite delete_item() erroring with not-found.
        svc.delete("missing")


def test_missing_credentials_raises_azure_credential_error():
    from agentx.azure.cosmos import CosmosService

    with pytest.raises(AzureCredentialError):
        CosmosService(database="my-db")


def test_endpoint_key_uses_key_auth():
    with mock.patch("azure.cosmos.CosmosClient") as MockClient:
        container = _make_mock_container()
        _wire_mock_client(MockClient, container)

        from agentx.azure.cosmos import CosmosService

        CosmosService(
            database="my-db",
            endpoint="https://acct.documents.azure.com:443/",
            key="my-key",
        )

        _, kwargs = MockClient.call_args
        assert kwargs["url"] == "https://acct.documents.azure.com:443/"
        assert kwargs["credential"] == "my-key"


def test_endpoint_only_uses_default_credential(monkeypatch: pytest.MonkeyPatch):
    fake_credential = mock.MagicMock(name="fake-default-credential")
    monkeypatch.setattr(
        "agentx.azure.cosmos.get_default_credential",
        lambda settings=None: fake_credential,
    )

    with mock.patch("azure.cosmos.CosmosClient") as MockClient:
        container = _make_mock_container()
        _wire_mock_client(MockClient, container)

        from agentx.azure.cosmos import CosmosService

        CosmosService(database="my-db", endpoint="https://acct.documents.azure.com:443/")

        _, kwargs = MockClient.call_args
        assert kwargs["url"] == "https://acct.documents.azure.com:443/"
        assert kwargs["credential"] is fake_credential
