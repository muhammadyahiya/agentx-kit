"""RAG: chunk documents, index them, retrieve relevant passages.

Uses Chroma when ``agentx-kit[rag]`` is installed; otherwise falls back to a
dependency-free in-memory keyword retriever so RAG works out of the box.
"""
from .pipeline import RagIndex, build_index_from_texts, make_retriever_tool

__all__ = ["RagIndex", "build_index_from_texts", "make_retriever_tool"]
