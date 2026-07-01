"""RAG pipeline with proper chunking, FAISS/Chroma vector store, and document loaders.

Strategy:
  1. Load documents via ``loaders.load_document()`` or ``load_directory()``.
  2. Chunk every text with ``RecursiveCharacterTextSplitter`` (LangChain).
  3. Embed chunks with the configured (or auto-detected) embedding provider.
  4. Store in FAISS (local, no server) or Chroma (persistent, richer filtering).
  5. Fall back to in-memory keyword retrieval when no embeddings are available.
"""
from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from ..config import get_settings

logger = logging.getLogger(__name__)

VectorStore = Literal["faiss", "chroma", "memory"]


# ──────────────────────────────────────────────────────────────────────────────
# Pydantic config for the pipeline
# ──────────────────────────────────────────────────────────────────────────────

class RAGConfig(BaseModel):
    """Configuration for the RAG pipeline build step.

    Invariants (enforced at construction time):
      chunk_size > 0
      0 <= chunk_overlap < chunk_size
    """

    chunk_size: int = Field(
        default=800, gt=0, description="Token/character target per chunk (> 0).",
    )
    chunk_overlap: int = Field(
        default=120, ge=0, description="Overlap between adjacent chunks (>= 0, < chunk_size).",
    )
    vector_store: VectorStore = Field(
        default="chroma",
        description="Vector store backend: 'faiss', 'chroma', or 'memory' (keyword fallback)",
    )
    persist_dir: str | None = Field(
        default=None,
        description="Directory to persist the index (FAISS: .faiss/, Chroma: .chroma/)",
    )
    collection_name: str = Field(default="agentx", description="Chroma collection name")

    model_config = {"extra": "allow"}

    @model_validator(mode="after")
    def _check_overlap_lt_chunk_size(self) -> "RAGConfig":
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError(
                f"chunk_overlap ({self.chunk_overlap}) must be < chunk_size ({self.chunk_size}); "
                "otherwise chunking cannot make progress."
            )
        return self


# ──────────────────────────────────────────────────────────────────────────────
# Chunking
# ──────────────────────────────────────────────────────────────────────────────

def chunk_texts(
    texts: list[str],
    chunk_size: int = 800,
    chunk_overlap: int = 120,
) -> list[str]:
    """Split ``texts`` into overlapping chunks using LangChain's splitter.

    Falls back to a simple character splitter when ``langchain-text-splitters``
    is not installed — but the LangChain version is strongly preferred because it
    respects sentence and paragraph boundaries.

    Raises:
        ValueError: if chunk_size <= 0 or chunk_overlap < 0 or chunk_overlap >= chunk_size.
    """
    if chunk_size <= 0:
        raise ValueError(f"chunk_size must be > 0 (got {chunk_size})")
    if chunk_overlap < 0:
        raise ValueError(f"chunk_overlap must be >= 0 (got {chunk_overlap})")
    if chunk_overlap >= chunk_size:
        raise ValueError(
            f"chunk_overlap ({chunk_overlap}) must be < chunk_size ({chunk_size})"
        )

    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter  # type: ignore

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", "! ", "? ", " ", ""],
        )
        all_chunks: list[str] = []
        for text in texts:
            chunks = splitter.split_text(text)
            all_chunks.extend(c for c in chunks if c.strip())
        logger.debug(
            "Chunked %d text(s) → %d chunks (size=%d overlap=%d, splitter=RecursiveCharacter)",
            len(texts), len(all_chunks), chunk_size, chunk_overlap,
        )
        return all_chunks
    except ImportError:
        logger.warning(
            "langchain-text-splitters not installed; using simple character chunker. "
            "Install 'agentx-kit[rag]' for better chunking."
        )

    # Fallback: simple fixed-size chunker.  Step is guaranteed > 0 because we
    # validated chunk_overlap < chunk_size above.
    step = chunk_size - chunk_overlap
    all_chunks: list[str] = []
    for text in texts:
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunk = text[start:end].strip()
            if chunk:
                all_chunks.append(chunk)
            start += step
    logger.debug(
        "Chunked %d text(s) → %d chunks (simple fallback)", len(texts), len(all_chunks)
    )
    return all_chunks


# ──────────────────────────────────────────────────────────────────────────────
# Keyword retrieval fallback
# ──────────────────────────────────────────────────────────────────────────────

_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(s: str) -> list[str]:
    return [t for t in _TOKEN.findall(s.lower()) if len(t) > 1]


# ──────────────────────────────────────────────────────────────────────────────
# RagIndex
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class RagIndex:
    """Holds chunks and answers similarity queries.

    Backed by a FAISS or Chroma vector store when available; otherwise falls
    back to an in-memory keyword scorer. The public ``search`` / ``context``
    API is identical in both modes.
    """

    chunks: list[str] = field(default_factory=list)
    _store: object | None = None
    _store_type: str = "memory"

    def search(self, query: str, k: int = 4) -> list[str]:
        """Return the top-k most relevant chunks for ``query``.

        Args:
            query: Free-text query.  Whitespace-only queries return [].
            k: Max number of chunks to return. Values < 1 return [].

        The vector store is used when available; on failure or when unavailable,
        falls back to token-frequency keyword scoring.  When no query token
        matches any chunk, an empty list is returned (previously the first N
        chunks were returned regardless of relevance).
        """
        if k < 1:
            return []
        if not query or not query.strip():
            return []
        if self._store is not None:
            try:
                docs = self._store.similarity_search(query, k=k)
                return [d.page_content for d in docs]
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Vector search (%s) failed, falling back to keyword: %s",
                    self._store_type, exc,
                )
        # Keyword fallback
        if not self.chunks:
            return []
        q = Counter(_tokens(query))
        if not q:
            return []
        scored = [(sum(_tokens(c).count(t) for t in q), c) for c in self.chunks]
        scored.sort(key=lambda x: x[0], reverse=True)
        top = [c for s, c in scored if s > 0][:k]
        if not top:
            logger.debug(
                "Keyword search: no tokens from %r matched any chunk (k=%d)", query, k
            )
        return top

    def context(self, query: str, k: int = 4) -> str:
        """Return search results joined for injection into a prompt."""
        return "\n---\n".join(self.search(query, k))

    @property
    def store_type(self) -> str:
        return self._store_type

    def __len__(self) -> int:
        return len(self.chunks)


# ──────────────────────────────────────────────────────────────────────────────
# Vector store builders
# ──────────────────────────────────────────────────────────────────────────────

def _build_faiss(chunks: list[str], embeddings, persist_dir: str | None) -> object | None:
    """Build (or load) a FAISS index.

    SECURITY NOTE: Loading a persisted FAISS index invokes pickle deserialization,
    which can execute arbitrary code if the on-disk file is untrusted.  We gate
    this behind ``AGENTX_FAISS_ALLOW_DANGEROUS_LOAD=1`` and emit a WARNING log
    every time the flag is honoured.  If the flag is false (default), a stale
    index on disk is rebuilt from scratch instead of loaded.
    """
    try:
        from langchain_community.vectorstores import FAISS  # type: ignore
    except ImportError:
        logger.warning(
            "FAISS not installed. Install 'agentx-kit[faiss]' for FAISS vector store."
        )
        return None

    pdir = Path(persist_dir) if persist_dir else None

    # Load from disk if index already exists (only if user opted in).
    if pdir and (pdir / "index.faiss").exists():
        allow_load = get_settings().faiss_allow_dangerous_load
        if not allow_load:
            logger.warning(
                "Refusing to load FAISS index from %s — pickle deserialization "
                "is disabled by default. Set AGENTX_FAISS_ALLOW_DANGEROUS_LOAD=1 "
                "if you trust the source of this index. Rebuilding from scratch.",
                pdir,
            )
        else:
            logger.warning(
                "Loading FAISS index from %s with pickle deserialization enabled "
                "(AGENTX_FAISS_ALLOW_DANGEROUS_LOAD=1). Trust the source of this file!",
                pdir,
            )
            try:
                store = FAISS.load_local(
                    str(pdir), embeddings, allow_dangerous_deserialization=True
                )
                logger.info("Loaded FAISS index from %s (%d chunks)", pdir, len(chunks))
                return store
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to load existing FAISS index: %s — rebuilding.", exc)

    store = FAISS.from_texts(chunks, embedding=embeddings)
    if pdir:
        pdir.mkdir(parents=True, exist_ok=True)
        store.save_local(str(pdir))
        logger.info("Built and saved FAISS index → %s", pdir)
    else:
        logger.info("Built in-memory FAISS index (%d chunks)", len(chunks))
    return store


def _build_chroma(
    chunks: list[str],
    embeddings,
    persist_dir: str | None,
    collection_name: str,
) -> object | None:
    """Build (or connect to) a Chroma index."""
    try:
        from langchain_chroma import Chroma  # type: ignore
    except ImportError:
        try:
            from langchain_community.vectorstores import Chroma  # type: ignore
        except ImportError:
            logger.warning(
                "Chroma not installed. Install 'agentx-kit[rag]' for Chroma vector store."
            )
            return None

    store = Chroma.from_texts(
        chunks,
        embedding=embeddings,
        persist_directory=persist_dir,
        collection_name=collection_name,
    )
    logger.info(
        "Built Chroma index: %d chunks, collection=%s, persist=%s",
        len(chunks), collection_name, persist_dir or "in-memory",
    )
    return store


# ──────────────────────────────────────────────────────────────────────────────
# Public builder
# ──────────────────────────────────────────────────────────────────────────────

def build_index_from_texts(
    texts: list[str],
    *,
    config: RAGConfig | None = None,
    # Legacy / convenience params (override config when set)
    persist_dir: str | None = None,
    vector_store: VectorStore | None = None,
    embeddings=None,
    embedding_config=None,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> RagIndex:
    """Build a ``RagIndex`` from raw text strings.

    Args:
        texts: Documents / passages to index.  Each string may be multiple
               paragraphs; they will be split into overlapping chunks.
        config: ``RAGConfig`` Pydantic model (controls chunk size, vector store,
                persist dir).  Individual keyword args override config values.
        persist_dir: Directory to persist the index on disk.
        vector_store: ``"faiss"``, ``"chroma"``, or ``"memory"``.
        embeddings: Pre-built LangChain ``Embeddings`` instance (takes priority
                    over ``embedding_config``).
        embedding_config: ``EmbeddingConfig`` subclass — built via
                          ``get_embeddings()``.  Falls back to auto-detection.
        chunk_size: Override the chunk character size.
        chunk_overlap: Override the chunk overlap.

    Returns:
        ``RagIndex`` backed by FAISS, Chroma, or keyword retrieval.
    """
    cfg = config or RAGConfig()

    # Keyword overrides — use ``is None`` to allow explicit 0/empty values.
    _chunk_size = chunk_size if chunk_size is not None else cfg.chunk_size
    _chunk_overlap = chunk_overlap if chunk_overlap is not None else cfg.chunk_overlap
    _vector_store = vector_store if vector_store is not None else cfg.vector_store
    _persist_dir = persist_dir if persist_dir is not None else cfg.persist_dir

    # 1. Chunk
    chunks = chunk_texts(texts, chunk_size=_chunk_size, chunk_overlap=_chunk_overlap)
    if not chunks:
        logger.warning("No text content after chunking; returning empty index.")
        return RagIndex(chunks=[], _store=None, _store_type="memory")

    logger.info(
        "Building RAG index: %d chunks, vector_store=%s", len(chunks), _vector_store
    )

    # 2. Resolve embeddings
    if _vector_store == "memory":
        logger.info("Using in-memory keyword retrieval (no embeddings)")
        return RagIndex(chunks=chunks, _store=None, _store_type="memory")

    if embeddings is None:
        from .embeddings import get_embeddings  # lazy import
        embeddings = get_embeddings(embedding_config or _settings_embedding_config())

    if embeddings is None:
        logger.warning(
            "No embedding provider available; falling back to keyword retrieval. "
            "Install 'agentx-kit[huggingface]' for free local embeddings."
        )
        return RagIndex(chunks=chunks, _store=None, _store_type="memory")

    # 3. Build vector store
    store = None
    store_type = "memory"
    try:
        if _vector_store == "faiss":
            store = _build_faiss(chunks, embeddings, _persist_dir)
            store_type = "faiss"
        else:  # chroma (default)
            store = _build_chroma(
                chunks, embeddings, _persist_dir, cfg.collection_name
            )
            store_type = "chroma"
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Vector store build failed (%s); falling back to keyword retrieval.", exc
        )

    if store is None:
        store_type = "memory"

    return RagIndex(chunks=chunks, _store=store, _store_type=store_type)


def build_index_from_files(
    paths: list[str | Path],
    *,
    config: RAGConfig | None = None,
    loader_config=None,
    **kwargs,
) -> RagIndex:
    """Load documents from file paths and build a ``RagIndex``.

    Convenience wrapper around ``load_document()`` + ``build_index_from_texts()``.
    Supports PDF, Excel, CSV, Word, TXT, Markdown.

    Args:
        paths: File paths to load.
        config: ``RAGConfig`` for the pipeline.
        loader_config: ``LoaderConfig`` for the document loaders.
        **kwargs: Forwarded to ``build_index_from_texts()``.
    """
    from .loaders import LoaderConfig, load_document  # lazy import

    lcfg = loader_config or LoaderConfig()
    all_texts: list[str] = []
    for p in paths:
        try:
            texts = load_document(p, lcfg)
            all_texts.extend(texts)
            logger.debug("Loaded %d section(s) from '%s'", len(texts), Path(p).name)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load '%s': %s", p, exc)

    if not all_texts:
        logger.warning("No content loaded from %d file(s).", len(paths))
    return build_index_from_texts(all_texts, config=config, **kwargs)


def build_index_from_directory(
    directory: str | Path,
    *,
    config: RAGConfig | None = None,
    loader_config=None,
    glob: str = "**/*",
    **kwargs,
) -> RagIndex:
    """Recursively load all supported documents from a directory."""
    from .loaders import LoaderConfig, load_directory  # lazy import

    lcfg = loader_config or LoaderConfig()
    doc_map = load_directory(directory, config=lcfg, glob=glob)
    all_texts = [text for pages in doc_map.values() for text in pages]
    logger.info(
        "Loaded %d document(s) from '%s' → %d text sections",
        len(doc_map), directory, len(all_texts),
    )
    return build_index_from_texts(all_texts, config=config, **kwargs)


def _settings_embedding_config():
    """Read AGENTX_EMBEDDING_PROVIDER / AGENTX_EMBEDDING_MODEL from settings."""
    from .embeddings import embedding_config_from_name

    s = get_settings()
    provider = s.default_embedding_provider.strip().lower()
    model = s.default_embedding_model.strip() or None

    cfg = embedding_config_from_name(provider, model=model)
    if cfg is not None:
        logger.debug(
            "Settings embedding: provider=%s model=%s",
            provider, model or "(default)",
        )
    return cfg


# ──────────────────────────────────────────────────────────────────────────────
# LangChain tool adapter
# ──────────────────────────────────────────────────────────────────────────────

def make_retriever_tool(index: RagIndex):
    """Expose a ``RagIndex`` as a LangChain ``@tool``."""
    from langchain_core.tools import tool

    @tool
    def knowledge_base(query: str) -> str:
        """Search the project's knowledge base and return relevant passages."""
        return index.context(query)

    return knowledge_base
