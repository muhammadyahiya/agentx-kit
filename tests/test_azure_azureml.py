"""Mock-based unit tests for agentx.azure.azureml — no live Azure calls.

azure-ai-ml is the heaviest optional dependency in this package, so every
test here importorskips it up front.
"""
from __future__ import annotations

import json
from unittest import mock

import pytest

pytest.importorskip("azure.ai.ml")

from agentx.azure.azureml import AzureMLService  # noqa: E402
from agentx.azure.config import reset_azure_settings  # noqa: E402
from agentx.azure.credentials import AzureCredentialError  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in ("AZURE_SUBSCRIPTION_ID", "AZURE_RESOURCE_GROUP", "AZURE_ML_WORKSPACE_NAME", "AZURE_CLIENT_ID"):
        monkeypatch.delenv(key, raising=False)
    reset_azure_settings()
    yield
    reset_azure_settings()


def _make_service(monkeypatch, **overrides):
    monkeypatch.setattr("agentx.azure.azureml.get_default_credential", lambda settings: object())
    kwargs = dict(
        endpoint="invoice-model",
        workspace_name="ws",
        subscription_id="sub-1",
        resource_group="rg-1",
    )
    kwargs.update(overrides)
    with mock.patch("azure.ai.ml.MLClient") as MockClient:
        service = AzureMLService(**kwargs)
        return service, MockClient


def test_missing_workspace_config_raises(monkeypatch):
    monkeypatch.setattr("agentx.azure.azureml.get_default_credential", lambda settings: object())
    with pytest.raises(AzureCredentialError):
        AzureMLService(endpoint="invoice-model")


def test_construct_builds_ml_client(monkeypatch):
    service, MockClient = _make_service(monkeypatch)
    MockClient.assert_called_once()
    _, kwargs = MockClient.call_args
    assert kwargs["subscription_id"] == "sub-1"
    assert kwargs["resource_group_name"] == "rg-1"
    assert kwargs["workspace_name"] == "ws"


def test_invoke_sends_json_and_parses_response(monkeypatch):
    service, MockClient = _make_service(monkeypatch)
    MockClient.return_value.online_endpoints.invoke.return_value = json.dumps({"prediction": 0.9})

    result = service.invoke({"text": "hello"}, deployment_name="blue")

    assert result == {"prediction": 0.9}
    _, kwargs = MockClient.return_value.online_endpoints.invoke.call_args
    assert kwargs["endpoint_name"] == "invoice-model"
    assert kwargs["deployment_name"] == "blue"
    assert json.loads(kwargs["input_data"]) == {"text": "hello"}


def test_invoke_returns_raw_when_not_json(monkeypatch):
    service, MockClient = _make_service(monkeypatch)
    MockClient.return_value.online_endpoints.invoke.return_value = "not json"
    assert service.invoke({"text": "hi"}) == "not json"


def test_submit_job_calls_jobs_create_or_update(monkeypatch):
    service, MockClient = _make_service(monkeypatch)
    mock_job = mock.MagicMock()
    MockClient.return_value.jobs.create_or_update.return_value = mock_job

    result = service.submit_job(
        code="./src", command="python train.py", compute="gpu-cluster", experiment_name="fraud",
    )

    assert result is mock_job
    MockClient.return_value.jobs.create_or_update.assert_called_once()


def test_register_model_calls_models_create_or_update(monkeypatch):
    service, MockClient = _make_service(monkeypatch)
    service.register_model("invoice-model", path="./model", version="3")
    MockClient.return_value.models.create_or_update.assert_called_once()


def test_deploy_model_calls_begin_create_or_update(monkeypatch):
    service, MockClient = _make_service(monkeypatch)
    mock_poller = mock.MagicMock()
    MockClient.return_value.online_deployments.begin_create_or_update.return_value = mock_poller

    service.deploy_model("blue", model="invoice-model:3")

    MockClient.return_value.online_deployments.begin_create_or_update.assert_called_once()
    mock_poller.result.assert_called_once()
