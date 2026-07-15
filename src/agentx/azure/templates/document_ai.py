"""DocumentAIPipeline — the spec's

    Blob + Service Bus + Container Apps + Azure AI Document Intelligence + Cosmos DB

shape: a document lands in Blob, a Service Bus message triggers extraction,
the structured result is persisted to Cosmos. Built directly on
``AIOpsPipeline`` (same queue-worker-Cosmos wiring) with a default processor
that calls Azure AI Document Intelligence instead of a chat model — override
with ``@pipeline.processor`` for custom extraction logic.
"""
from __future__ import annotations

from typing import Any

from .._logging import azure_logger
from ..config import AzureSettings
from .aiops import AIOpsPipeline

logger = azure_logger("templates.document_ai")


class DocumentAIPipeline(AIOpsPipeline):
    def __init__(
        self,
        name: str,
        storage: str,
        queue: str,
        workers: int = 1,
        model_id: str = "prebuilt-document",
        document_intelligence_endpoint: str | None = None,
        cosmos_database: str | None = None,
        settings: AzureSettings | None = None,
        credential: Any = None,
    ):
        super().__init__(
            name=name, storage=storage, queue=queue, workers=workers,
            cosmos_database=cosmos_database, settings=settings, credential=credential,
        )
        self.model_id = model_id
        self.document_intelligence_endpoint = document_intelligence_endpoint

    def _default_processor(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Extract structured fields from the blob named in ``payload['blob_name']``
        via Azure AI Document Intelligence."""
        try:
            from azure.ai.documentintelligence import DocumentIntelligenceClient
        except ImportError as exc:
            raise RuntimeError(
                "azure-ai-documentintelligence is not installed. Run "
                "`pip install 'agentx-kit[azure-documentai]'`."
            ) from exc

        if not self.document_intelligence_endpoint:
            raise RuntimeError("DocumentAIPipeline requires document_intelligence_endpoint.")

        from ..credentials import get_default_credential

        blob_name = payload["blob_name"]
        data = self.blob.download(blob_name)
        client = DocumentIntelligenceClient(
            endpoint=self.document_intelligence_endpoint,
            credential=self._credential or get_default_credential(self._settings),
        )
        poller = client.begin_analyze_document(self.model_id, body=data)
        result = poller.result()
        fields = {
            name: field.value_string or field.content
            for doc in getattr(result, "documents", None) or []
            for name, field in (doc.fields or {}).items()
        }
        return {"blob_name": blob_name, "model_id": self.model_id, "fields": fields}
