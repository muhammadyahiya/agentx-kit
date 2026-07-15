"""Mock-based unit tests for agentx.azure.templates.rag.RAGPipeline."""
from __future__ import annotations

from unittest import mock

import pytest

pytest.importorskip("azure.storage.blob")

from agentx.azure.config import reset_azure_settings  # noqa: E402
from agentx.azure.templates.rag import RAGPipeline  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
    monkeypatch.delenv("AZURE_CLIENT_ID", raising=False)
    reset_azure_settings()
    yield
    reset_azure_settings()


def _fake_settings():
    return mock.Mock(
        storage_connection_string="DefaultEndpointsProtocol=https;AccountName=x;AccountKey=y;EndpointSuffix=core.windows.net",
        retry_total=5, retry_backoff_seconds=0.8,
    )


def test_upload_documents_uploads_every_file(tmp_path):
    (tmp_path / "a.txt").write_text("hello")
    (tmp_path / "b.txt").write_text("world")

    with mock.patch("azure.storage.blob.BlobServiceClient") as MockClient:
        container = MockClient.from_connection_string.return_value.get_container_client.return_value
        container.upload_blob.return_value.url = "https://x/blob"

        pipeline = RAGPipeline(documents=str(tmp_path), settings=_fake_settings())
        urls = pipeline.upload_documents(tmp_path)

        assert urls == ["https://x/blob", "https://x/blob"]
        assert container.upload_blob.call_count == 2


def test_ingest_builds_index_from_downloaded_blobs(monkeypatch):
    with mock.patch("azure.storage.blob.BlobServiceClient") as MockClient:
        container = MockClient.from_connection_string.return_value.get_container_client.return_value
        container.list_blobs.return_value = [mock.Mock(name="doc1.txt")]
        container.list_blobs.return_value[0].name = "doc1.txt"
        container.download_blob.return_value.readall.return_value = b"hello world"

        mock_index = object()
        mock_build = mock.Mock(return_value=mock_index)
        monkeypatch.setattr("agentx.rag.build_index_from_texts", mock_build)

        pipeline = RAGPipeline(documents="pdf/", vector_store="memory", settings=_fake_settings())
        result = pipeline.ingest()

        assert result is mock_index
        assert pipeline.index is mock_index
        mock_build.assert_called_once()
        (texts,), kwargs = mock_build.call_args
        assert texts == ["hello world"]
        assert kwargs["vector_store"] == "memory"


def test_deploy_without_output_dir_only_returns_manifest():
    pipeline = RAGPipeline(documents="pdf/", settings=_fake_settings())
    result = pipeline.deploy(name="rag-service")
    assert result["project_dir"] is None
    assert result["manifest"]["name"] == "rag-service"


def test_deploy_with_output_dir_scaffolds_project(monkeypatch, tmp_path):
    mock_result = mock.Mock(target_dir=tmp_path / "rag-service")
    mock_generate = mock.Mock(return_value=mock_result)
    monkeypatch.setattr("agentx.scaffold.generate_project", mock_generate)

    pipeline = RAGPipeline(documents="pdf/", settings=_fake_settings())
    result = pipeline.deploy(name="rag-service", output_dir=tmp_path / "out")

    mock_generate.assert_called_once()
    spec_arg = mock_generate.call_args[0][0]
    assert spec_arg.name == "rag-service"
    assert spec_arg.use_rag is True
    assert result["project_dir"] == str(tmp_path / "rag-service")
