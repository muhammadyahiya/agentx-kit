"""``AzurePipeline`` — the fluent, few-lines-of-code entry point for wiring
Azure services into a production AI pipeline (the "Spring Boot for Azure AI"
developer experience):

    from agentx.azure import AzurePipeline

    pipeline = (
        AzurePipeline(name="document-processing")
        .blob_storage(container="documents")
        .service_bus(queue="document-queue")
        .container_app(image="processor:latest")
        .azure_ml(endpoint="invoice-model")
        .cosmosdb(database="documents")
    )
    pipeline.deploy()               # plan only (safe, no Azure calls, no creds needed)
    pipeline.deploy(execute=True)    # actually wire each step

Every ``.xxx(...)`` call just records a declarative *step*; nothing touches
Azure until ``.deploy()`` runs, and ``deploy()`` defaults to a dry-run
plan — the enterprise "plan before apply" pattern (à la Terraform). Pass
``execute=True`` once real credentials are configured (Managed Identity, or a
service's connection string/key via env vars — see ``agentx.azure.config``)
to actually instantiate each step's wrapper.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from ._logging import azure_logger, correlation_scope

logger = azure_logger("pipeline")


@dataclass
class PipelineStep:
    kind: str
    config: dict[str, Any]
    result: Any = field(default=None, repr=False)  # populated by deploy(execute=True)


class AzurePipeline:
    """Fluent builder chaining Azure services into one deployable pipeline."""

    def __init__(self, name: str):
        self.name = name
        self.steps: list[PipelineStep] = []

    def _add(self, kind: str, **config: Any) -> "AzurePipeline":
        self.steps.append(PipelineStep(kind=kind, config=config))
        return self

    # ---- declarative step builders (chainable) ----
    def blob_storage(self, container: str, **kwargs: Any) -> "AzurePipeline":
        return self._add("blob_storage", container=container, **kwargs)

    def service_bus(self, queue: str, **kwargs: Any) -> "AzurePipeline":
        return self._add("service_bus", queue=queue, **kwargs)

    def container_app(self, image: str, **kwargs: Any) -> "AzurePipeline":
        return self._add("container_app", image=image, **kwargs)

    def azure_ml(self, endpoint: str, **kwargs: Any) -> "AzurePipeline":
        return self._add("azure_ml", endpoint=endpoint, **kwargs)

    def cosmosdb(self, database: str, **kwargs: Any) -> "AzurePipeline":
        return self._add("cosmosdb", database=database, **kwargs)

    def key_vault(self, vault_url: str, **kwargs: Any) -> "AzurePipeline":
        return self._add("key_vault", vault_url=vault_url, **kwargs)

    def event_grid(self, topic: str, **kwargs: Any) -> "AzurePipeline":
        return self._add("event_grid", topic=topic, **kwargs)

    def monitor(self, **kwargs: Any) -> "AzurePipeline":
        return self._add("monitor", **kwargs)

    # ---- execution ----
    def plan(self) -> list[dict[str, Any]]:
        """Return the ordered list of steps this pipeline would provision/wire."""
        return [{"kind": s.kind, **s.config} for s in self.steps]

    def deploy(self, execute: bool = False) -> "AzurePipeline":
        """Run every step in order.

        ``execute=False`` (default): log the plan only — no Azure calls, no
        credentials required.
        ``execute=True``: instantiate each step's wrapper for real (requires
        the matching ``agentx-kit[azure-*]`` extra + credentials/env vars).
        """
        with correlation_scope() as cid:
            logger.info(
                "Pipeline '%s' %s (%d steps)",
                self.name, "executing" if execute else "planned", len(self.steps),
                extra={"correlation_id": cid, "service": "pipeline", "operation": "deploy",
                       "pipeline": self.name, "execute": execute},
            )
            for step in self.steps:
                logger.info(
                    "  step: %s(%s)", step.kind, step.config,
                    extra={"correlation_id": cid, "service": "pipeline", "operation": step.kind},
                )
                if execute:
                    step.result = _WIRERS[step.kind](step.config)
        return self

    def __repr__(self) -> str:
        return f"AzurePipeline(name={self.name!r}, steps={[s.kind for s in self.steps]})"


def _wire_blob_storage(config: dict[str, Any]) -> Any:
    from .blob import BlobStorageService

    return BlobStorageService(**config)


def _wire_service_bus(config: dict[str, Any]) -> Any:
    from .servicebus import ServiceBusQueue

    return ServiceBusQueue(**config)


def _wire_cosmosdb(config: dict[str, Any]) -> Any:
    from .cosmos import CosmosService

    return CosmosService(**config)


def _wire_key_vault(config: dict[str, Any]) -> Any:
    from .keyvault import KeyVaultService

    return KeyVaultService(**config)


def _wire_event_grid(config: dict[str, Any]) -> Any:
    from .eventgrid import EventGridService

    return EventGridService(**config)


def _wire_container_app(config: dict[str, Any]) -> Any:
    from .containerapp import ContainerAppService

    return ContainerAppService(**config)


def _wire_azure_ml(config: dict[str, Any]) -> Any:
    from .azureml import AzureMLService

    return AzureMLService(**config)


def _wire_monitor(config: dict[str, Any]) -> Any:
    from .monitor import setup_azure_monitor

    setup_azure_monitor(**config)
    return None


_WIRERS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "blob_storage": _wire_blob_storage,
    "service_bus": _wire_service_bus,
    "cosmosdb": _wire_cosmosdb,
    "key_vault": _wire_key_vault,
    "event_grid": _wire_event_grid,
    "container_app": _wire_container_app,
    "azure_ml": _wire_azure_ml,
    "monitor": _wire_monitor,
}
