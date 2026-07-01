"""RAG: chunk documents, embed, store in FAISS/Chroma, and retrieve.

Supports PDF, Excel, CSV, Word, TXT, Markdown via ``loaders.load_document()``.
Uses LangChain's ``RecursiveCharacterTextSplitter`` for chunking.
8 embedding providers via Pydantic config classes.
Choice of FAISS or Chroma vector stores.
"""
from .embeddings import (
    AnyEmbeddingConfig,
    AzureOpenAIEmbeddingConfig,
    BedrockEmbeddingConfig,
    CohereEmbeddingConfig,
    EmbeddingConfig,
    GoogleEmbeddingConfig,
    HuggingFaceEmbeddingConfig,
    OllamaEmbeddingConfig,
    OpenAIEmbeddingConfig,
    VoyageEmbeddingConfig,
    auto_embeddings,
    get_embeddings,
)
from .loaders import LoaderConfig, load_directory, load_document
from .pipeline import (
    RAGConfig,
    RagIndex,
    build_index_from_directory,
    build_index_from_files,
    build_index_from_texts,
    chunk_texts,
    make_retriever_tool,
)

__all__ = [
    # Pipeline
    "RagIndex",
    "RAGConfig",
    "build_index_from_texts",
    "build_index_from_files",
    "build_index_from_directory",
    "chunk_texts",
    "make_retriever_tool",
    # Loaders
    "load_document",
    "load_directory",
    "LoaderConfig",
    # Embedding factory
    "get_embeddings",
    "auto_embeddings",
    # Embedding configs
    "EmbeddingConfig",
    "AnyEmbeddingConfig",
    "HuggingFaceEmbeddingConfig",
    "OpenAIEmbeddingConfig",
    "AzureOpenAIEmbeddingConfig",
    "CohereEmbeddingConfig",
    "GoogleEmbeddingConfig",
    "BedrockEmbeddingConfig",
    "VoyageEmbeddingConfig",
    "OllamaEmbeddingConfig",
]
