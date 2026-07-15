"""Unit tests for agentx.azure.eventgrid.EventGridService — mocked, no live Azure calls.

``azure.eventgrid`` is imported lazily inside ``EventGridService.__init__``,
so there is no module-level name in ``agentx.azure.eventgrid`` to patch;
instead we patch the real SDK class where it actually lives
(``azure.eventgrid.EventGridPublisherClient``). ``CloudEvent`` is a lightweight
dataclass-like object from ``azure.core.messaging`` — safe to construct for
real and inspect rather than mock.
"""
from __future__ import annotations

from unittest import mock

import pytest

pytest.importorskip("azure.eventgrid")

from agentx.azure.config import reset_azure_settings  # noqa: E402
from agentx.azure.credentials import AzureCredentialError  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_azure_env(monkeypatch: pytest.MonkeyPatch):
    """Ensure no ambient AZURE_EVENTGRID_* env leaks between tests."""
    for key in (
        "AZURE_EVENTGRID_TOPIC_ENDPOINT",
        "AZURE_EVENTGRID_TOPIC_KEY",
        "AZURE_CLIENT_ID",
    ):
        monkeypatch.delenv(key, raising=False)
    reset_azure_settings()
    yield
    reset_azure_settings()


def test_construct_with_topic_endpoint_and_key_uses_key_credential():
    with (
        mock.patch("azure.eventgrid.EventGridPublisherClient") as MockClient,
        mock.patch("azure.core.credentials.AzureKeyCredential") as MockKeyCredential,
    ):
        fake_credential = mock.MagicMock(name="fake-key-credential")
        MockKeyCredential.return_value = fake_credential

        from agentx.azure.eventgrid import EventGridService

        EventGridService(
            topic="document-processing",
            topic_endpoint="https://my-topic.eastus-1.eventgrid.azure.net/api/events",
            topic_key="super-secret-key",
        )

        MockKeyCredential.assert_called_once_with("super-secret-key")
        MockClient.assert_called_once()
        args, _ = MockClient.call_args
        assert args[0] == "https://my-topic.eastus-1.eventgrid.azure.net/api/events"
        assert args[1] is fake_credential


def test_publish_happy_path():
    with mock.patch("azure.eventgrid.EventGridPublisherClient") as MockClient:
        client = mock.MagicMock()
        MockClient.return_value = client

        from agentx.azure.eventgrid import EventGridService

        svc = EventGridService(
            topic="document-processing",
            topic_endpoint="https://my-topic.eastus-1.eventgrid.azure.net/api/events",
            topic_key="super-secret-key",
        )

        svc.publish("document.created", {"id": "doc-1"}, subject="docs/doc-1")

        client.send.assert_called_once()
        (sent_events,), _kwargs = client.send.call_args
        assert isinstance(sent_events, list)
        assert len(sent_events) == 1
        event = sent_events[0]
        assert event.source == "document-processing"
        assert event.type == "document.created"
        assert event.data == {"id": "doc-1"}
        assert event.subject == "docs/doc-1"


def test_account_url_uses_default_credential_when_no_key(monkeypatch: pytest.MonkeyPatch):
    fake_credential = mock.MagicMock(name="fake-default-credential")
    monkeypatch.setattr(
        "agentx.azure.eventgrid.get_default_credential",
        lambda settings=None: fake_credential,
    )

    with mock.patch("azure.eventgrid.EventGridPublisherClient") as MockClient:
        from agentx.azure.eventgrid import EventGridService

        EventGridService(
            topic="document-processing",
            topic_endpoint="https://my-topic.eastus-1.eventgrid.azure.net/api/events",
        )

        args, _ = MockClient.call_args
        assert args[0] == "https://my-topic.eastus-1.eventgrid.azure.net/api/events"
        assert args[1] is fake_credential


def test_missing_topic_endpoint_raises_azure_credential_error():
    from agentx.azure.eventgrid import EventGridService

    with pytest.raises(AzureCredentialError):
        EventGridService(topic="document-processing")
