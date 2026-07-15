"""Mock-based unit tests for agentx.azure.servicebus — no live Azure calls."""
from __future__ import annotations

from unittest import mock

import pytest

pytest.importorskip("azure.servicebus")

from agentx.azure.config import reset_azure_settings  # noqa: E402
from agentx.azure.credentials import AzureCredentialError  # noqa: E402
from agentx.azure.servicebus import ServiceBusQueue  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in ("AZURE_SERVICEBUS_CONNECTION_STRING", "AZURE_SERVICEBUS_NAMESPACE", "AZURE_CLIENT_ID"):
        monkeypatch.delenv(key, raising=False)
    reset_azure_settings()
    yield
    reset_azure_settings()


def test_construct_with_connection_string():
    with mock.patch("azure.servicebus.ServiceBusClient") as MockClient:
        MockClient.from_connection_string.return_value = mock.MagicMock()
        queue = ServiceBusQueue("invoice", connection_string="Endpoint=sb://test/;SharedAccessKey=x")
        MockClient.from_connection_string.assert_called_once()
        assert queue.queue == "invoice"


def test_construct_with_namespace_uses_default_credential(monkeypatch):
    fake_credential = object()
    monkeypatch.setattr("agentx.azure.servicebus.get_default_credential", lambda settings: fake_credential)
    with mock.patch("azure.servicebus.ServiceBusClient") as MockClient:
        ServiceBusQueue("invoice", namespace="myns")
        _, kwargs = MockClient.call_args
        assert kwargs["fully_qualified_namespace"] == "myns.servicebus.windows.net"
        assert kwargs["credential"] is fake_credential


def test_missing_credentials_raises_azure_credential_error():
    with pytest.raises(AzureCredentialError):
        ServiceBusQueue("invoice")


def test_send_serializes_dict_and_sets_correlation_id():
    with mock.patch("azure.servicebus.ServiceBusClient") as MockClient:
        mock_sender = mock.MagicMock()
        mock_sender.__enter__.return_value = mock_sender
        MockClient.from_connection_string.return_value.get_queue_sender.return_value = mock_sender

        queue = ServiceBusQueue("invoice", connection_string="Endpoint=sb://test/;SharedAccessKey=x")
        queue.send({"job_id": "abc"})

        mock_sender.send_messages.assert_called_once()
        (sent_message,), _ = mock_sender.send_messages.call_args
        assert sent_message.body == b'{"job_id": "abc"}' or b"".join(sent_message.body) == b'{"job_id": "abc"}'


def test_listen_completes_on_success():
    class FakeMessage:
        delivery_count = 0

        def __str__(self):
            return '{"job_id": "abc"}'

    with mock.patch("azure.servicebus.ServiceBusClient") as MockClient:
        mock_receiver = mock.MagicMock()
        mock_receiver.__enter__.return_value = mock_receiver
        mock_receiver.__iter__.return_value = iter([FakeMessage()])
        MockClient.from_connection_string.return_value.get_queue_receiver.return_value = mock_receiver

        queue = ServiceBusQueue("invoice", connection_string="Endpoint=sb://test/;SharedAccessKey=x")
        seen = []
        queue.consumer(lambda data: seen.append(data))
        processed = queue.listen()

        assert processed == 1
        assert seen == [{"job_id": "abc"}]
        mock_receiver.complete_message.assert_called_once()
        mock_receiver.abandon_message.assert_not_called()
        mock_receiver.dead_letter_message.assert_not_called()


def test_listen_dead_letters_after_max_delivery_attempts():
    class FakeMessage:
        delivery_count = 5  # >= default max_delivery_attempts

        def __str__(self):
            return "not json"

    with mock.patch("azure.servicebus.ServiceBusClient") as MockClient:
        mock_receiver = mock.MagicMock()
        mock_receiver.__enter__.return_value = mock_receiver
        mock_receiver.__iter__.return_value = iter([FakeMessage()])
        MockClient.from_connection_string.return_value.get_queue_receiver.return_value = mock_receiver

        queue = ServiceBusQueue("invoice", connection_string="Endpoint=sb://test/;SharedAccessKey=x")

        def _fail(data):
            raise ValueError("boom")

        queue.consumer(_fail)
        processed = queue.listen()

        assert processed == 1
        mock_receiver.dead_letter_message.assert_called_once()
        mock_receiver.complete_message.assert_not_called()


def test_listen_abandons_below_max_delivery_attempts():
    class FakeMessage:
        delivery_count = 1

        def __str__(self):
            return "not json"

    with mock.patch("azure.servicebus.ServiceBusClient") as MockClient:
        mock_receiver = mock.MagicMock()
        mock_receiver.__enter__.return_value = mock_receiver
        mock_receiver.__iter__.return_value = iter([FakeMessage()])
        MockClient.from_connection_string.return_value.get_queue_receiver.return_value = mock_receiver

        queue = ServiceBusQueue("invoice", connection_string="Endpoint=sb://test/;SharedAccessKey=x")
        queue.consumer(lambda data: (_ for _ in ()).throw(ValueError("boom")))
        queue.listen()

        mock_receiver.abandon_message.assert_called_once()
        mock_receiver.dead_letter_message.assert_not_called()


def test_listen_without_consumer_raises():
    with mock.patch("azure.servicebus.ServiceBusClient"):
        queue = ServiceBusQueue("invoice", connection_string="Endpoint=sb://test/;SharedAccessKey=x")
        with pytest.raises(RuntimeError):
            queue.listen()
