"""Tests for agentx.azure.containerapp — manifest generation is pure Python
(no Azure SDK, no mocking needed); ``deploy()`` is mock-based since it requires
azure-mgmt-appcontainers + a live subscription."""
from __future__ import annotations

import json
from unittest import mock

import pytest

from agentx.azure.config import reset_azure_settings
from agentx.azure.containerapp import ContainerAppService
from agentx.azure.credentials import AzureCredentialError


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in ("AZURE_SUBSCRIPTION_ID", "AZURE_RESOURCE_GROUP", "AZURE_CLIENT_ID"):
        monkeypatch.delenv(key, raising=False)
    reset_azure_settings()
    yield
    reset_azure_settings()


def test_generate_dockerfile_has_healthcheck_and_cmd():
    svc = ContainerAppService(image="processor:latest")
    dockerfile = svc.generate_dockerfile()
    assert "FROM python:3.12-slim" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert 'CMD ["python", "main.py"]' in dockerfile


def test_generate_manifest_includes_managed_identity_and_probes():
    svc = ContainerAppService(image="processor:latest", cpu=2, memory="4Gi", min_replicas=1, max_replicas=20)
    manifest = svc.generate_manifest("processor")

    assert manifest["identity"] == {"type": "SystemAssigned"}
    container = manifest["properties"]["template"]["containers"][0]
    assert container["image"] == "processor:latest"
    assert container["resources"] == {"cpu": 2, "memory": "4Gi"}
    probe_types = {p["type"] for p in container["probes"]}
    assert probe_types == {"Liveness", "Readiness"}
    scale = manifest["properties"]["template"]["scale"]
    assert scale["minReplicas"] == 1
    assert scale["maxReplicas"] == 20


def test_generate_manifest_adds_servicebus_keda_rule_when_queue_set():
    svc = ContainerAppService(image="processor:latest", queue_name="document-queue", queue_length_threshold=10)
    manifest = svc.generate_manifest("processor")
    rules = manifest["properties"]["template"]["scale"]["rules"]
    keda_rule = next(r for r in rules if r["name"] == "servicebus-queue-scale")
    assert keda_rule["custom"]["type"] == "azure-servicebus"
    assert keda_rule["custom"]["metadata"]["queueName"] == "document-queue"
    assert keda_rule["custom"]["metadata"]["messageCount"] == "10"


def test_generate_manifest_no_rules_when_autoscale_disabled():
    svc = ContainerAppService(image="processor:latest", autoscale=False, queue_name="q")
    manifest = svc.generate_manifest("processor")
    assert manifest["properties"]["template"]["scale"]["rules"] == []


def test_write_manifests_writes_dockerfile_and_json(tmp_path):
    svc = ContainerAppService(image="processor:latest")
    paths = svc.write_manifests(tmp_path, "processor")

    assert len(paths) == 2
    dockerfile_path, manifest_path = paths
    assert dockerfile_path.name == "Dockerfile"
    assert manifest_path.name == "containerapp.json"
    assert dockerfile_path.read_text().startswith("FROM")
    manifest = json.loads(manifest_path.read_text())
    assert manifest["name"] == "processor"


def test_deploy_without_subscription_raises():
    svc = ContainerAppService(image="processor:latest")
    with pytest.raises(AzureCredentialError):
        svc.deploy("processor")


def test_remove_calls_begin_delete(monkeypatch):
    pytest.importorskip("azure.mgmt.appcontainers")
    monkeypatch.setattr("agentx.azure.containerapp.get_default_credential", lambda settings: object())

    svc = ContainerAppService(image="processor:latest", subscription_id="sub-1", resource_group="rg-1")
    with mock.patch("azure.mgmt.appcontainers.ContainerAppsAPIClient") as MockClient:
        mock_poller = mock.MagicMock()
        MockClient.return_value.container_apps.begin_delete.return_value = mock_poller

        svc.remove("processor")

        MockClient.return_value.container_apps.begin_delete.assert_called_once_with(
            resource_group_name="rg-1", container_app_name="processor",
        )
        mock_poller.result.assert_called_once()


def test_remove_without_subscription_raises():
    svc = ContainerAppService(image="processor:latest")
    with pytest.raises(AzureCredentialError):
        svc.remove("processor")


def test_deploy_calls_mgmt_client(monkeypatch):
    pytest.importorskip("azure.mgmt.appcontainers")
    fake_credential = object()
    monkeypatch.setattr("agentx.azure.containerapp.get_default_credential", lambda settings: fake_credential)

    svc = ContainerAppService(
        image="processor:latest", subscription_id="sub-1", resource_group="rg-1",
    )
    with mock.patch("azure.mgmt.appcontainers.ContainerAppsAPIClient") as MockClient:
        mock_poller = mock.MagicMock()
        MockClient.return_value.container_apps.begin_create_or_update.return_value = mock_poller

        svc.deploy("processor", environment_id="/subscriptions/sub-1/.../managedEnvironments/env")

        MockClient.assert_called_once()
        _, kwargs = MockClient.call_args
        assert kwargs["subscription_id"] == "sub-1"
        assert kwargs["credential"] is fake_credential
        MockClient.return_value.container_apps.begin_create_or_update.assert_called_once()
        mock_poller.result.assert_called_once()
