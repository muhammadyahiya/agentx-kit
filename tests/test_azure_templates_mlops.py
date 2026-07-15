"""Mock-based unit tests for agentx.azure.templates.mlops.MLOpsPipeline."""
from __future__ import annotations

from unittest import mock

import pytest

pytest.importorskip("azure.ai.ml")
pytest.importorskip("azure.storage.blob")

from agentx.azure.config import reset_azure_settings  # noqa: E402
from agentx.azure.templates.mlops import MLOpsPipeline  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in (
        "AZURE_SUBSCRIPTION_ID", "AZURE_RESOURCE_GROUP", "AZURE_ML_WORKSPACE_NAME",
        "AZURE_STORAGE_CONNECTION_STRING", "AZURE_CLIENT_ID",
    ):
        monkeypatch.delenv(key, raising=False)
    reset_azure_settings()
    yield
    reset_azure_settings()


def _make_pipeline(monkeypatch):
    monkeypatch.setattr("agentx.azure.azureml.get_default_credential", lambda settings: object())
    return MLOpsPipeline(
        dataset="customer.csv", experiment="fraud", compute="gpu-cluster",
        workspace_name="ws", subscription_id="sub-1", resource_group="rg-1",
    )


def test_upload_dataset_uses_blob_service(monkeypatch):
    pipeline = _make_pipeline(monkeypatch)
    with mock.patch("azure.storage.blob.BlobServiceClient") as MockClient:
        MockClient.from_connection_string.return_value.get_container_client.return_value.upload_blob.return_value.url = "https://x/customer.csv"
        pipeline._settings.storage_connection_string = "DefaultEndpointsProtocol=https;AccountName=x;AccountKey=y;EndpointSuffix=core.windows.net"
        url = pipeline.upload_dataset(b"a,b,c\n1,2,3")
        assert url == "https://x/customer.csv"


def test_train_submits_job(monkeypatch):
    pipeline = _make_pipeline(monkeypatch)
    with mock.patch("azure.ai.ml.MLClient") as MockClient:
        mock_job = mock.MagicMock()
        MockClient.return_value.jobs.create_or_update.return_value = mock_job

        result = pipeline.train(code="./src", command="python train.py")

        assert result is mock_job
        assert pipeline.last_job is mock_job
        MockClient.return_value.jobs.create_or_update.assert_called_once()


def test_register_then_deploy_uses_versioned_model_ref(monkeypatch):
    pipeline = _make_pipeline(monkeypatch)
    with mock.patch("azure.ai.ml.MLClient") as MockClient:
        pipeline.register_model(path="./model", version="3")
        MockClient.return_value.models.create_or_update.assert_called_once()

        mock_poller = mock.MagicMock()
        MockClient.return_value.online_deployments.begin_create_or_update.return_value = mock_poller

        pipeline.deploy()

        deployment_arg = MockClient.return_value.online_deployments.begin_create_or_update.call_args[0][0]
        assert deployment_arg.model == "fraud:3"


def test_monitor_drift_does_not_raise():
    with mock.patch("agentx.azure.azureml.get_default_credential", lambda settings: object()):
        pipeline = MLOpsPipeline(
            dataset="customer.csv", experiment="fraud",
            workspace_name="ws", subscription_id="sub-1", resource_group="rg-1",
        )
        pipeline.monitor_drift("accuracy", 0.94)
