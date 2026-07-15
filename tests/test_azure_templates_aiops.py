"""Mock-based unit tests for agentx.azure.templates.aiops.AIOpsPipeline."""
from __future__ import annotations

from unittest import mock

import pytest

pytest.importorskip("azure.storage.blob")
pytest.importorskip("azure.servicebus")
pytest.importorskip("azure.cosmos")

from agentx.azure.config import reset_azure_settings  # noqa: E402
from agentx.azure.templates.aiops import AIOpsPipeline  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in (
        "AZURE_STORAGE_CONNECTION_STRING", "AZURE_SERVICEBUS_CONNECTION_STRING",
        "AZURE_COSMOS_CONNECTION_STRING", "AZURE_CLIENT_ID",
    ):
        monkeypatch.delenv(key, raising=False)
    reset_azure_settings()
    yield
    reset_azure_settings()


def test_write_manifests_needs_no_credentials(tmp_path):
    pipeline = AIOpsPipeline(name="claims-ai", storage="claims", queue="claim-queue", workers=5)
    paths = pipeline.write_manifests(tmp_path)
    assert {p.name for p in paths} == {"Dockerfile", "containerapp.json"}


def test_run_with_custom_processor_upserts_to_cosmos():
    with mock.patch("azure.servicebus.ServiceBusClient") as MockBus, mock.patch("azure.cosmos.CosmosClient") as MockCosmos:
        mock_receiver = mock.MagicMock()
        mock_receiver.__enter__.return_value = mock_receiver

        class FakeMessage:
            delivery_count = 0

            def __str__(self):
                return '{"job_id": "job-1", "text": "hello"}'

        mock_receiver.__iter__.return_value = iter([FakeMessage()])
        MockBus.from_connection_string.return_value.get_queue_receiver.return_value = mock_receiver

        pipeline = AIOpsPipeline(
            name="claims-ai", storage="claims", queue="claim-queue",
            settings=mock.Mock(
                storage_connection_string=None, servicebus_connection_string="Endpoint=sb://x/;SharedAccessKey=y",
                cosmos_connection_string="AccountEndpoint=https://x/;AccountKey=y",
                retry_total=5, retry_backoff_seconds=0.8,
            ),
        )

        @pipeline.processor
        def process(payload):
            return {"result": payload["text"].upper()}

        processed = pipeline.run()

        assert processed == 1
        upsert_call = MockCosmos.from_connection_string.return_value.create_database_if_not_exists.return_value \
            .create_container_if_not_exists.return_value.upsert_item
        upsert_call.assert_called_once()
        (doc,), _ = upsert_call.call_args
        assert doc["result"] == "HELLO"
        assert doc["id"] == "job-1"


def test_default_processor_calls_azure_chat_model():
    fake_settings = mock.Mock(
        storage_connection_string=None,
        servicebus_connection_string="Endpoint=sb://x/;SharedAccessKey=y",
        cosmos_connection_string="AccountEndpoint=https://x/;AccountKey=y",
        retry_total=5, retry_backoff_seconds=0.8,
    )
    with mock.patch("azure.servicebus.ServiceBusClient") as MockBus, \
         mock.patch("azure.cosmos.CosmosClient"), \
         mock.patch("agentx.providers.get_chat_model") as mock_get_chat_model:
        mock_llm = mock.MagicMock()
        mock_llm.invoke.return_value = mock.Mock(content="42")
        mock_get_chat_model.return_value = mock_llm

        mock_receiver = mock.MagicMock()
        mock_receiver.__enter__.return_value = mock_receiver

        class FakeMessage:
            delivery_count = 0

            def __str__(self):
                return '{"job_id": "job-1", "text": "what is the answer"}'

        mock_receiver.__iter__.return_value = iter([FakeMessage()])
        MockBus.from_connection_string.return_value.get_queue_receiver.return_value = mock_receiver

        pipeline = AIOpsPipeline(
            name="claims-ai", storage="claims", queue="claim-queue",
            ai_endpoint="gpt4o", settings=fake_settings,
        )
        pipeline.run()

        mock_get_chat_model.assert_called_once_with("azure", model="gpt4o")
        mock_llm.invoke.assert_called_once_with("what is the answer")
