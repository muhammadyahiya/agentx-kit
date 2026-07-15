"""Mock-based unit tests for agentx.azure.keyvault — no live Azure calls."""
from __future__ import annotations

from unittest import mock

import pytest

pytest.importorskip("azure.keyvault.secrets")

from agentx.azure.config import reset_azure_settings  # noqa: E402
from agentx.azure.credentials import AzureCredentialError  # noqa: E402
from agentx.azure.keyvault import KeyVaultService  # noqa: E402


def _fake_credential():
    return object()


def test_construct_with_vault_url_and_credential():
    with mock.patch("azure.keyvault.secrets.SecretClient") as MockClient:
        service = KeyVaultService(
            vault_url="https://fake-vault.vault.azure.net/",
            credential=_fake_credential(),
        )
        assert service is not None
        MockClient.assert_called_once()


def test_get_secret_happy_path():
    with mock.patch("azure.keyvault.secrets.SecretClient") as MockClient:
        MockClient.return_value.get_secret.return_value = mock.Mock(value="s3cr3t")
        service = KeyVaultService(
            vault_url="https://fake-vault.vault.azure.net/",
            credential=_fake_credential(),
        )

        assert service.get_secret("my-secret") == "s3cr3t"
        MockClient.return_value.get_secret.assert_called_once_with("my-secret")


def test_get_secret_uses_cache_until_invalidated():
    with mock.patch("azure.keyvault.secrets.SecretClient") as MockClient:
        MockClient.return_value.get_secret.return_value = mock.Mock(value="s3cr3t")
        service = KeyVaultService(
            vault_url="https://fake-vault.vault.azure.net/",
            credential=_fake_credential(),
        )

        assert service.get_secret("my-secret") == "s3cr3t"
        assert service.get_secret("my-secret") == "s3cr3t"
        assert MockClient.return_value.get_secret.call_count == 1

        service.invalidate_cache("my-secret")

        assert service.get_secret("my-secret") == "s3cr3t"
        assert MockClient.return_value.get_secret.call_count == 2


def test_set_secret_updates_cache_without_fresh_get_call():
    with mock.patch("azure.keyvault.secrets.SecretClient") as MockClient:
        MockClient.return_value.get_secret.return_value = mock.Mock(value="old-value")
        service = KeyVaultService(
            vault_url="https://fake-vault.vault.azure.net/",
            credential=_fake_credential(),
        )

        assert service.get_secret("my-secret") == "old-value"
        assert MockClient.return_value.get_secret.call_count == 1

        service.set_secret("my-secret", "new-value")
        MockClient.return_value.set_secret.assert_called_once_with("my-secret", "new-value")

        assert service.get_secret("my-secret") == "new-value"
        # Still only the one call from before set_secret — cache served this read.
        assert MockClient.return_value.get_secret.call_count == 1


def test_missing_vault_url_raises_credential_error(monkeypatch):
    monkeypatch.delenv("AZURE_KEYVAULT_URL", raising=False)
    reset_azure_settings()
    try:
        with mock.patch("azure.keyvault.secrets.SecretClient"):
            with pytest.raises(AzureCredentialError):
                KeyVaultService(credential=_fake_credential())
    finally:
        reset_azure_settings()
