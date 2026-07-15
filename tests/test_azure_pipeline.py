"""Unit tests for agentx.azure.pipeline.AzurePipeline — the fluent builder.

``deploy(execute=False)`` (the default) never touches Azure or any wrapper
module, so most of this file needs no mocking at all; ``execute=True`` is
covered by monkeypatching the per-step wirer functions.
"""
from __future__ import annotations

import agentx.azure.pipeline as pipeline_mod
from agentx.azure.pipeline import AzurePipeline


def test_fluent_chain_records_steps_in_order():
    pipeline = (
        AzurePipeline(name="document-processing")
        .blob_storage(container="documents")
        .service_bus(queue="document-queue")
        .container_app(image="processor:latest")
        .azure_ml(endpoint="invoice-model")
        .cosmosdb(database="documents")
    )
    assert [s.kind for s in pipeline.steps] == [
        "blob_storage", "service_bus", "container_app", "azure_ml", "cosmosdb",
    ]
    assert pipeline.plan() == [
        {"kind": "blob_storage", "container": "documents"},
        {"kind": "service_bus", "queue": "document-queue"},
        {"kind": "container_app", "image": "processor:latest"},
        {"kind": "azure_ml", "endpoint": "invoice-model"},
        {"kind": "cosmosdb", "database": "documents"},
    ]


def test_deploy_dry_run_does_not_touch_azure():
    pipeline = AzurePipeline(name="p").blob_storage(container="c").service_bus(queue="q")
    pipeline.deploy()  # execute=False by default
    assert all(step.result is None for step in pipeline.steps)


def test_deploy_execute_wires_each_step(monkeypatch):
    calls = []

    def fake_wire_blob(config):
        calls.append(("blob_storage", config))
        return "blob-service"

    def fake_wire_bus(config):
        calls.append(("service_bus", config))
        return "bus-queue"

    monkeypatch.setitem(pipeline_mod._WIRERS, "blob_storage", fake_wire_blob)
    monkeypatch.setitem(pipeline_mod._WIRERS, "service_bus", fake_wire_bus)

    pipeline = AzurePipeline(name="p").blob_storage(container="c").service_bus(queue="q")
    pipeline.deploy(execute=True)

    assert calls == [("blob_storage", {"container": "c"}), ("service_bus", {"queue": "q"})]
    assert pipeline.steps[0].result == "blob-service"
    assert pipeline.steps[1].result == "bus-queue"


def test_all_step_builders_are_chainable_and_return_self():
    pipeline = AzurePipeline(name="p")
    result = pipeline.key_vault(vault_url="https://kv.vault.azure.net").event_grid(topic="t").monitor()
    assert result is pipeline
    assert [s.kind for s in pipeline.steps] == ["key_vault", "event_grid", "monitor"]


def test_repr_lists_step_kinds():
    pipeline = AzurePipeline(name="p").blob_storage(container="c")
    assert "blob_storage" in repr(pipeline)
    assert "p" in repr(pipeline)
