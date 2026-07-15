"""Unit tests for agentx.azure.yaml_config."""
from __future__ import annotations

from agentx.azure.yaml_config import build_pipeline_from_config, load_pipeline


def test_build_pipeline_wires_only_present_sections():
    config = {
        "pipeline": {"name": "claims-ai"},
        "storage": {"blob": "claims"},
        "queue": {"servicebus": "claim-queue"},
        "worker": {"replicas": 5},
        "database": {"cosmos": "claimsdb"},
        "monitoring": {"appinsights": True},
    }
    pipeline = build_pipeline_from_config(config)

    assert pipeline.name == "claims-ai"
    assert [s.kind for s in pipeline.steps] == ["blob_storage", "service_bus", "container_app", "cosmosdb", "monitor"]
    container_step = next(s for s in pipeline.steps if s.kind == "container_app")
    assert container_step.config == {"image": "claims-ai:latest", "max_replicas": 5}


def test_build_pipeline_skips_absent_sections():
    pipeline = build_pipeline_from_config({"pipeline": {"name": "p"}})
    assert pipeline.steps == []


def test_build_pipeline_defaults_name_when_missing():
    pipeline = build_pipeline_from_config({})
    assert pipeline.name == "pipeline"


def test_load_pipeline_from_yaml_file(tmp_path):
    yaml_path = tmp_path / "pipeline.yaml"
    yaml_path.write_text(
        "pipeline:\n  name: claims-ai\n"
        "storage:\n  blob: claims\n"
        "ml:\n  endpoint: invoice-model\n"
    )
    pipeline = load_pipeline(yaml_path)
    assert pipeline.name == "claims-ai"
    assert [s.kind for s in pipeline.steps] == ["blob_storage", "azure_ml"]
