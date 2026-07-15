"""Mock-based unit tests for agentx.azure.templates.chatbot.ChatbotPipeline."""
from __future__ import annotations

from unittest import mock

import pytest

pytest.importorskip("azure.cosmos")

from agentx.azure.config import reset_azure_settings  # noqa: E402
from agentx.azure.templates.chatbot import ChatbotPipeline  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("AZURE_COSMOS_CONNECTION_STRING", raising=False)
    monkeypatch.delenv("AZURE_CLIENT_ID", raising=False)
    reset_azure_settings()
    yield
    reset_azure_settings()


def _fake_settings():
    return mock.Mock(
        cosmos_connection_string="AccountEndpoint=https://x/;AccountKey=y",
        retry_total=5, retry_backoff_seconds=0.8,
    )


def test_history_empty_when_no_session_doc():
    with mock.patch("azure.cosmos.CosmosClient") as MockClient:
        from azure.cosmos import exceptions

        container = MockClient.from_connection_string.return_value.create_database_if_not_exists.return_value \
            .create_container_if_not_exists.return_value
        container.read_item.side_effect = exceptions.CosmosResourceNotFoundError()

        pipeline = ChatbotPipeline(name="support-bot", settings=_fake_settings())
        assert pipeline.history("session-1") == []


def test_send_appends_turn_and_persists(monkeypatch):
    with mock.patch("azure.cosmos.CosmosClient") as MockClient, \
         mock.patch("agentx.providers.get_chat_model") as mock_get_chat_model:
        from azure.cosmos import exceptions

        container = MockClient.from_connection_string.return_value.create_database_if_not_exists.return_value \
            .create_container_if_not_exists.return_value
        container.read_item.side_effect = exceptions.CosmosResourceNotFoundError()

        mock_llm = mock.MagicMock()
        mock_llm.invoke.return_value = mock.Mock(content="Hi there!")
        mock_get_chat_model.return_value = mock_llm

        pipeline = ChatbotPipeline(name="support-bot", model="gpt-4o", settings=_fake_settings())
        reply = pipeline.send("session-1", "hello")

        assert reply == "Hi there!"
        mock_get_chat_model.assert_called_once_with("azure", model="gpt-4o")
        container.upsert_item.assert_called_once()
        (doc,), _ = container.upsert_item.call_args
        assert doc["id"] == "session-1"
        assert doc["messages"] == [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
