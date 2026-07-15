"""Mock-based unit tests for agentx.azure.templates.document_ai.DocumentAIPipeline."""
from __future__ import annotations

from unittest import mock

import pytest

pytest.importorskip("azure.ai.documentintelligence")
pytest.importorskip("azure.storage.blob")
pytest.importorskip("azure.servicebus")
pytest.importorskip("azure.cosmos")

from agentx.azure.config import reset_azure_settings  # noqa: E402
from agentx.azure.templates.document_ai import DocumentAIPipeline  # noqa: E402


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


def _fake_settings():
    return mock.Mock(
        storage_connection_string="DefaultEndpointsProtocol=https;AccountName=x;AccountKey=y;EndpointSuffix=core.windows.net",
        servicebus_connection_string="Endpoint=sb://x/;SharedAccessKey=y",
        cosmos_connection_string="AccountEndpoint=https://x/;AccountKey=y",
        retry_total=5, retry_backoff_seconds=0.8,
    )


def test_missing_endpoint_raises():
    pipeline = DocumentAIPipeline(
        name="invoices", storage="invoices", queue="invoice-queue", settings=_fake_settings(),
    )
    with mock.patch("azure.storage.blob.BlobServiceClient"):
        with pytest.raises(RuntimeError):
            pipeline._default_processor({"blob_name": "invoice1.pdf"})


def test_default_processor_extracts_fields(monkeypatch):
    monkeypatch.setattr("agentx.azure.credentials.get_default_credential", lambda settings: object())

    with mock.patch("azure.storage.blob.BlobServiceClient") as MockBlob, \
         mock.patch("azure.ai.documentintelligence.DocumentIntelligenceClient") as MockDI:
        MockBlob.from_connection_string.return_value.get_container_client.return_value \
            .download_blob.return_value.readall.return_value = b"%PDF-1.4 fake bytes"

        mock_field = mock.Mock(value_string="Acme Corp", content="Acme Corp")
        mock_doc = mock.Mock(fields={"vendor_name": mock_field})
        mock_result = mock.Mock(documents=[mock_doc])
        MockDI.return_value.begin_analyze_document.return_value.result.return_value = mock_result

        pipeline = DocumentAIPipeline(
            name="invoices", storage="invoices", queue="invoice-queue",
            document_intelligence_endpoint="https://di.cognitiveservices.azure.com",
            settings=_fake_settings(),
        )
        result = pipeline._default_processor({"blob_name": "invoice1.pdf"})

        assert result["blob_name"] == "invoice1.pdf"
        assert result["fields"]["vendor_name"] == "Acme Corp"
        MockDI.return_value.begin_analyze_document.assert_called_once()
