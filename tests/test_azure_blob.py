"""Unit tests for agentx.azure.blob.BlobStorageService — mocked, no live Azure calls.

``azure.storage.blob`` is imported lazily inside ``BlobStorageService.__init__``,
so there is no module-level name in ``agentx.azure.blob`` to patch; instead we
patch the real SDK class where it actually lives (``azure.storage.blob.BlobServiceClient``).
"""
from __future__ import annotations

from unittest import mock

import pytest

pytest.importorskip("azure.storage.blob")

from agentx.azure.config import reset_azure_settings  # noqa: E402
from agentx.azure.credentials import AzureCredentialError  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_azure_env(monkeypatch: pytest.MonkeyPatch):
    """Ensure no ambient AZURE_STORAGE_* env leaks between tests."""
    for key in (
        "AZURE_STORAGE_CONNECTION_STRING",
        "AZURE_STORAGE_ACCOUNT_URL",
        "AZURE_CLIENT_ID",
    ):
        monkeypatch.delenv(key, raising=False)
    reset_azure_settings()
    yield
    reset_azure_settings()


def _make_mock_client() -> mock.MagicMock:
    """Build a MagicMock standing in for a constructed BlobServiceClient's container client."""
    container_client = mock.MagicMock()

    uploaded = mock.MagicMock()
    uploaded.url = "https://acct.blob.core.windows.net/container/blob.txt"
    container_client.upload_blob.return_value = uploaded

    downloaded = mock.MagicMock()
    downloaded.readall.return_value = b"hello world"
    container_client.download_blob.return_value = downloaded

    blob_a = mock.MagicMock()
    blob_a.name = "a.txt"
    blob_b = mock.MagicMock()
    blob_b.name = "b.txt"
    container_client.list_blobs.return_value = [blob_a, blob_b]

    blob_client = mock.MagicMock()
    blob_client.exists.return_value = True
    container_client.get_blob_client.return_value = blob_client

    return container_client


def test_construct_with_connection_string():
    with mock.patch("azure.storage.blob.BlobServiceClient") as MockClient:
        service_client = mock.MagicMock()
        container_client = _make_mock_client()
        service_client.get_container_client.return_value = container_client
        MockClient.from_connection_string.return_value = service_client

        from agentx.azure.blob import BlobStorageService

        svc = BlobStorageService(
            container="my-container",
            connection_string="DefaultEndpointsProtocol=https;AccountName=acct;AccountKey=key;EndpointSuffix=core.windows.net",
        )

        MockClient.from_connection_string.assert_called_once()
        service_client.get_container_client.assert_called_once_with("my-container")
        container_client.create_container.assert_called_once()
        assert svc._container_client is container_client


def test_upload_download_list_delete_exists_happy_path():
    with mock.patch("azure.storage.blob.BlobServiceClient") as MockClient:
        service_client = mock.MagicMock()
        container_client = _make_mock_client()
        service_client.get_container_client.return_value = container_client
        MockClient.from_connection_string.return_value = service_client

        from agentx.azure.blob import BlobStorageService

        svc = BlobStorageService(container="my-container", connection_string="cs")

        url = svc.upload("blob.txt", b"hello world", content_type="text/plain")
        assert url == "https://acct.blob.core.windows.net/container/blob.txt"
        container_client.upload_blob.assert_called_once()

        data = svc.download("blob.txt")
        assert data == b"hello world"

        names = svc.list_blobs(prefix="a")
        assert names == ["a.txt", "b.txt"]

        svc.delete("blob.txt")
        container_client.delete_blob.assert_called_once_with("blob.txt")

        assert svc.exists("blob.txt") is True


def test_create_container_already_exists_is_silent():
    from azure.core.exceptions import ResourceExistsError

    with mock.patch("azure.storage.blob.BlobServiceClient") as MockClient:
        service_client = mock.MagicMock()
        container_client = _make_mock_client()
        container_client.create_container.side_effect = ResourceExistsError("already exists")
        service_client.get_container_client.return_value = container_client
        MockClient.from_connection_string.return_value = service_client

        from agentx.azure.blob import BlobStorageService

        # Should not raise despite create_container() erroring.
        BlobStorageService(container="my-container", connection_string="cs")


def test_missing_credentials_raises_azure_credential_error():
    from agentx.azure.blob import BlobStorageService

    with pytest.raises(AzureCredentialError):
        BlobStorageService(container="my-container")


def test_account_url_uses_default_credential(monkeypatch: pytest.MonkeyPatch):
    fake_credential = mock.MagicMock(name="fake-default-credential")
    monkeypatch.setattr(
        "agentx.azure.blob.get_default_credential",
        lambda settings=None: fake_credential,
    )

    with mock.patch("azure.storage.blob.BlobServiceClient") as MockClient:
        service_client = mock.MagicMock()
        container_client = _make_mock_client()
        service_client.get_container_client.return_value = container_client
        MockClient.return_value = service_client

        from agentx.azure.blob import BlobStorageService

        BlobStorageService(container="my-container", account_url="https://acct.blob.core.windows.net")

        _, kwargs = MockClient.call_args
        assert kwargs["account_url"] == "https://acct.blob.core.windows.net"
        assert kwargs["credential"] is fake_credential
