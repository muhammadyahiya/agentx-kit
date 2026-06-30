"""A small, swappable RAG pipeline.

Strategy:
  * Split text into chunks (LangChain splitter if available, else a simple splitter).
  * Index with Chroma + embeddings when ``[rag]`` is installed.
  * Otherwise fall back to an in-memory keyword retriever (no deps), so the
    generated project runs immediately and can be upgraded later.
"""
from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


def _split(text: str, chunk_size: int = 800, overlap: int = 120) -> list[str]:
    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=overlap)
        return [c for c in splitter.split_text(text) if c.strip()]
    except ImportError:
        chunks, start = [], 0
        while start < len(text):
            chunks.append(text[start:start + chunk_size])
            start += chunk_size - overlap
        return [c for c in chunks if c.strip()]


_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(s: str) -> list[str]:
    return [t for t in _TOKEN.findall(s.lower()) if len(t) > 1]


@dataclass
class RagIndex:
    """Holds chunks and answers similarity queries.

    If a vector store is available it is used; otherwise a keyword scorer ranks
    chunks. The public ``search`` API is identical either way.
    """

    chunks: list[str] = field(default_factory=list)
    _store: object | None = None

    def search(self, query: str, k: int = 4) -> list[str]:
        if self._store is not None:
            try:
                docs = self._store.similarity_search(query, k=k)
                return [d.page_content for d in docs]
            except Exception as exc:  # noqa: BLE001
                logger.warning("Vector search failed, falling back to keyword: %s", exc)
        # Keyword fallback.
        if not self.chunks:
            return []
        q = Counter(_tokens(query))
        scored = [(sum(_tokens(c).count(t) for t in q), c) for c in self.chunks]
        scored.sort(key=lambda x: x[0], reverse=True)
        top = [c for s, c in scored if s > 0][:k]
        return top or self.chunks[:k]

    def context(self, query: str, k: int = 4) -> str:
        return "\n---\n".join(self.search(query, k))


def build_index_from_texts(texts: list[str], persist_dir: str | None = None, embeddings=None) -> RagIndex:
    """Build a ``RagIndex`` from raw texts; uses Chroma if installed."""
    chunks: list[str] = []
    for t in texts:
        chunks.extend(_split(t))

    store = None
    try:
        from langchain_chroma import Chroma  # type: ignore

        if embeddings is None:
            from langchain_core.embeddings import Embeddings  # noqa: F401
            embeddings = _default_embeddings()
        if embeddings is not None:
            store = Chroma.from_texts(chunks, embedding=embeddings, persist_directory=persist_dir)
    except ImportError:
        logger.info("Chroma not installed; using in-memory keyword retriever. Install 'agentx-kit[rag]' to upgrade.")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Vector index build failed (%s); using keyword retriever.", exc)

    return RagIndex(chunks=chunks, _store=store)


def _default_embeddings():
    """Best-effort embeddings: try a local/OpenAI embedder, else None (keyword mode)."""
    try:
        from langchain_openai import OpenAIEmbeddings  # type: ignore
        import os

        if os.getenv("OPENAI_API_KEY"):
            return OpenAIEmbeddings(model="text-embedding-3-small")
    except ImportError:
        pass
    try:
        from langchain_ollama import OllamaEmbeddings  # type: ignore

        return OllamaEmbeddings(model="nomic-embed-text")
    except ImportError:
        return None


def make_retriever_tool(index: RagIndex):
    """Expose a ``RagIndex`` as a LangChain retrieval ``@tool``."""
    from langchain_core.tools import tool

    @tool
    def knowledge_base(query: str) -> str:
        """Search the project's knowledge base and return relevant passages."""
        return index.context(query)

    return knowledge_base
