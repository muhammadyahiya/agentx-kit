"""Load an ``AzurePipeline`` from a declarative YAML file:

    pipeline:
      name: claims-ai
    storage:
      blob: claims
    queue:
      servicebus: claim-queue
    worker:
      replicas: 5
    ml:
      endpoint: invoice-model
    database:
      cosmos: claimsdb
    monitoring:
      appinsights: true

Every section is optional — only the steps present in the file are added to
the pipeline. ``pyyaml`` is lazy-imported here (not a core agentx-kit
dependency) since only the ``agentx azure`` CLI needs it.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .pipeline import AzurePipeline


def load_pipeline_config(path: str | Path) -> dict[str, Any]:
    """Parse the YAML file into a plain dict (no ``AzurePipeline`` built yet)."""
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError(
            "pyyaml is not installed. Run `pip install 'agentx-kit[azure-platform]'`."
        ) from exc

    text = Path(path).read_text()
    return yaml.safe_load(text) or {}


def build_pipeline_from_config(config: dict[str, Any]) -> AzurePipeline:
    """Build an ``AzurePipeline`` from an already-parsed config dict."""
    name = (config.get("pipeline") or {}).get("name", "pipeline")
    pipeline = AzurePipeline(name=name)

    storage = config.get("storage") or {}
    if storage.get("blob"):
        pipeline.blob_storage(container=storage["blob"])

    queue = config.get("queue") or {}
    if queue.get("servicebus"):
        pipeline.service_bus(queue=queue["servicebus"])

    worker = config.get("worker") or {}
    if worker:
        pipeline.container_app(image=f"{name}:latest", max_replicas=worker.get("replicas", 1))

    ml = config.get("ml") or {}
    if ml.get("endpoint"):
        pipeline.azure_ml(endpoint=ml["endpoint"])

    database = config.get("database") or {}
    if database.get("cosmos"):
        pipeline.cosmosdb(database=database["cosmos"])

    if (config.get("monitoring") or {}).get("appinsights"):
        pipeline.monitor()

    return pipeline


def load_pipeline(path: str | Path) -> AzurePipeline:
    """Parse a YAML pipeline file and build the ``AzurePipeline`` in one call."""
    return build_pipeline_from_config(load_pipeline_config(path))
