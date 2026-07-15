"""AIOpsPipeline — the queue-driven "AI worker" shape: a message lands on
Service Bus, gets processed (by default: sent to Azure OpenAI), the result is
persisted to Cosmos DB, and a metric is emitted — with retry/DLQ handled by
the underlying ``ServiceBusQueue`` and structured logging/correlation IDs on
every step, matching the spec's

    Blob Storage -> Service Bus -> Container App -> Azure OpenAI -> CosmosDB
    -> Monitoring -> Retry -> Dead Letter Queue

``AIOpsPipeline`` *is* the worker body that runs inside that Container App —
:meth:`write_manifests` generates the Container App/Dockerfile to deploy it,
:meth:`run` is what that container's entrypoint calls.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .._logging import azure_logger
from ..blob import BlobStorageService
from ..config import AzureSettings, get_azure_settings
from ..containerapp import ContainerAppService
from ..cosmos import CosmosService
from ..monitor import emit_metric
from ..servicebus import ServiceBusQueue

logger = azure_logger("templates.aiops")


class AIOpsPipeline:
    def __init__(
        self,
        name: str,
        storage: str,
        queue: str,
        workers: int = 1,
        ai_endpoint: str | None = None,
        cosmos_database: str | None = None,
        settings: AzureSettings | None = None,
        credential: Any = None,
    ):
        self.name = name
        self.storage = storage
        self.queue = queue
        self.workers = workers
        self.ai_endpoint = ai_endpoint
        self.cosmos_database = cosmos_database or f"{name}-db"
        self._settings = settings or get_azure_settings()
        self._credential = credential
        self._processor: Callable[[dict[str, Any]], dict[str, Any]] | None = None
        self._blob: BlobStorageService | None = None
        self._bus: ServiceBusQueue | None = None
        self._cosmos: CosmosService | None = None

    def processor(self, fn: Callable[[dict[str, Any]], dict[str, Any]]) -> Callable[[dict[str, Any]], dict[str, Any]]:
        """Decorator: register the function that turns one queued job into a result dict.

        Without one registered, :meth:`run` sends the payload straight to
        ``ai_endpoint`` via Azure OpenAI (the doc's zero-code default).
        """
        self._processor = fn
        return fn

    def _blob_service(self) -> BlobStorageService:
        if self._blob is None:
            self._blob = BlobStorageService(container=self.storage, settings=self._settings, credential=self._credential)
        return self._blob

    def _bus_service(self) -> ServiceBusQueue:
        if self._bus is None:
            self._bus = ServiceBusQueue(queue=self.queue, settings=self._settings, credential=self._credential)
        return self._bus

    def _cosmos_service(self) -> CosmosService:
        if self._cosmos is None:
            self._cosmos = CosmosService(database=self.cosmos_database, settings=self._settings, credential=self._credential)
        return self._cosmos

    @property
    def blob(self) -> BlobStorageService:
        return self._blob_service()

    def _default_processor(self, payload: dict[str, Any]) -> dict[str, Any]:
        from ...providers import get_chat_model

        llm = get_chat_model("azure", model=self.ai_endpoint)
        text = payload.get("text") or payload.get("content") or str(payload)
        response = llm.invoke(text)
        return {"input": payload, "output": getattr(response, "content", str(response))}

    def write_manifests(self, output_dir: str | Path) -> list[Path]:
        """Generate the Dockerfile + Container App manifest for this worker
        (KEDA-scaled on ``self.queue``'s length, ``max_replicas=self.workers``)."""
        container = ContainerAppService(
            image=f"{self.name}:latest", max_replicas=self.workers, queue_name=self.queue,
        )
        return container.write_manifests(output_dir, self.name)

    def run(self, max_messages: int | None = None) -> int:
        """Start consuming ``self.queue``: processor -> Cosmos upsert -> metric,
        with the registered handler's failures retried/dead-lettered by
        ``ServiceBusQueue.listen`` automatically. Returns the count processed."""
        processor = self._processor or self._default_processor
        bus = self._bus_service()
        cosmos = self._cosmos_service()

        def handler(payload: dict[str, Any]) -> dict[str, Any]:
            result = processor(payload)
            doc = {**result, "id": payload.get("job_id") or result.get("id")}
            if not doc.get("id"):
                import uuid

                doc["id"] = uuid.uuid4().hex
            cosmos.upsert(doc)
            emit_metric("aiops.jobs_processed", 1, pipeline=self.name)
            return result

        bus.consumer(handler)
        return bus.listen(max_messages=max_messages)
