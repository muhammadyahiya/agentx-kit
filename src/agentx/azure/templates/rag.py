"""RAGPipeline — Blob (source docs) -> chunk -> embed -> vector index -> deploy,
matching the spec's

    Blob -> Document Intelligence -> Chunking -> Embedding -> Azure AI Search
    -> Azure OpenAI -> Container App

Reuses ``agentx.rag`` (the same chunking/embedding/FAISS-Chroma stack every
other agentx project uses) rather than reinventing it — the only Azure-specific
part is sourcing documents from Blob Storage instead of the local filesystem.
Azure AI Search as a vector-store backend is not wired yet (only FAISS/Chroma/
in-memory keyword retrieval, same as ``agentx.rag``) — see docs/azure.md.
``deploy()`` hands off to agentx's own project scaffolder to produce a
ready-to-run FastAPI+RAG service plus its Container App manifest, instead of
duplicating that machinery here.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .._logging import azure_logger
from ..blob import BlobStorageService
from ..config import AzureSettings, get_azure_settings

logger = azure_logger("templates.rag")


class RAGPipeline:
    def __init__(
        self,
        documents: str,
        embedding_model: str = "text-embedding-3-large",
        llm: str = "gpt-4o",
        container: str = "rag-documents",
        vector_store: str = "faiss",
        settings: AzureSettings | None = None,
        credential: Any = None,
    ):
        self.documents = documents
        self.embedding_model = embedding_model
        self.llm = llm
        self.container = container
        self.vector_store = vector_store
        self._settings = settings or get_azure_settings()
        self._credential = credential
        self._blob: BlobStorageService | None = None
        self.index: Any = None

    def _blob_service(self) -> BlobStorageService:
        if self._blob is None:
            self._blob = BlobStorageService(container=self.container, settings=self._settings, credential=self._credential)
        return self._blob

    def upload_documents(self, directory: str | Path) -> list[str]:
        """Upload every file in a local directory to the Blob documents container; returns their URLs."""
        blob = self._blob_service()
        urls = []
        for path in sorted(Path(directory).iterdir()):
            if path.is_file():
                urls.append(blob.upload(path.name, path.read_bytes()))
        return urls

    def ingest(self, prefix: str | None = None) -> Any:
        """Download blobs, chunk + embed them, and build a retrieval index
        (``agentx.rag.build_index_from_texts`` — FAISS/Chroma, auto-detected
        embedding provider unless one is configured for ``self.embedding_model``)."""
        from ...rag import build_index_from_texts

        blob = self._blob_service()
        names = blob.list_blobs(prefix=prefix)
        texts = [blob.download(name).decode("utf-8", errors="ignore") for name in names]
        self.index = build_index_from_texts(texts, vector_store=self.vector_store)
        return self.index

    def deploy(self, name: str = "rag-service", output_dir: str | Path | None = None) -> dict[str, Any]:
        """Scaffold a ready-to-run FastAPI+RAG service (agentx's own project
        generator, Azure OpenAI + Azure embeddings preselected) and generate its
        Container App manifest. Pass ``output_dir`` to actually write the project
        to disk; omitted, only the Container App manifest is returned."""
        from ..containerapp import ContainerAppService

        project_dir = None
        if output_dir is not None:
            from ...scaffold import ProjectSpec, generate_project

            spec = ProjectSpec(
                name=name,
                provider="azure",
                model=self.llm,
                use_rag=True,
                embedding_provider="azure",
                embedding_model=self.embedding_model,
                serve=True,
                docker=True,
                ci=True,
            )
            result = generate_project(spec, output_dir)
            project_dir = str(getattr(result, "target_dir", output_dir))

        container = ContainerAppService(image=f"{name}:latest")
        return {"project_dir": project_dir, "manifest": container.generate_manifest(name)}
