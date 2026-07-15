"""Unit tests for the `agentx azure` CLI (typer.testing.CliRunner)."""
from __future__ import annotations

from unittest import mock

from typer.testing import CliRunner

from agentx.azure.cli import azure_app

runner = CliRunner()


def test_init_writes_pipeline_yaml_and_env_example(tmp_path):
    result = runner.invoke(azure_app, ["init", "--name", "claims-ai", "--output", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "pipeline.yaml").exists()
    assert (tmp_path / ".env.example").exists()
    assert "claims-ai" in (tmp_path / "pipeline.yaml").read_text()
    assert "AZURE_STORAGE_CONNECTION_STRING" in (tmp_path / ".env.example").read_text()


def test_create_unknown_template_errors():
    result = runner.invoke(azure_app, ["create", "not-a-template"])
    assert result.exit_code != 0


def test_create_writes_starter_file(tmp_path):
    target = tmp_path / "worker.py"
    result = runner.invoke(azure_app, ["create", "aiops", "--name", "claims-ai", "--output", str(target)])
    assert result.exit_code == 0, result.output
    content = target.read_text()
    assert "AIOpsPipeline" in content
    assert "agentx.azure.templates" in content


def test_plan_prints_steps(tmp_path):
    yaml_path = tmp_path / "pipeline.yaml"
    yaml_path.write_text("pipeline:\n  name: claims-ai\nstorage:\n  blob: claims\n")
    result = runner.invoke(azure_app, ["plan", str(yaml_path)])
    assert result.exit_code == 0, result.output
    assert "blob_storage" in result.output
    assert "claims" in result.output


def test_deploy_defaults_to_plan_only(tmp_path):
    yaml_path = tmp_path / "pipeline.yaml"
    yaml_path.write_text("pipeline:\n  name: claims-ai\nstorage:\n  blob: claims\n")
    result = runner.invoke(azure_app, ["deploy", str(yaml_path)])
    assert result.exit_code == 0, result.output
    assert "planned" in result.output


def test_deploy_execute_wires_steps(tmp_path, monkeypatch):
    import agentx.azure.pipeline as pipeline_mod

    called = []
    monkeypatch.setitem(pipeline_mod._WIRERS, "blob_storage", lambda config: called.append(config) or "wired")

    yaml_path = tmp_path / "pipeline.yaml"
    yaml_path.write_text("pipeline:\n  name: claims-ai\nstorage:\n  blob: claims\n")
    result = runner.invoke(azure_app, ["deploy", str(yaml_path), "--execute"])

    assert result.exit_code == 0, result.output
    assert "executed" in result.output
    assert called == [{"container": "claims"}]


def test_destroy_without_yes_aborts_on_no():
    result = runner.invoke(azure_app, ["destroy", "processor"], input="n\n")
    assert result.exit_code != 0


def test_destroy_with_yes_calls_remove(monkeypatch):
    mock_remove = mock.Mock()
    monkeypatch.setattr("agentx.azure.containerapp.ContainerAppService.remove", mock_remove)
    result = runner.invoke(azure_app, ["destroy", "processor", "--yes", "--resource-group", "rg-1"])
    assert result.exit_code == 0, result.output
    mock_remove.assert_called_once_with("processor")
