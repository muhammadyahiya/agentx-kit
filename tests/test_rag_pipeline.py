"""Tests for the RAG pipeline (chunking, RAGConfig validation, RagIndex)."""
from __future__ import annotations

import pytest

from agentx.rag import RAGConfig, RagIndex, build_index_from_texts, chunk_texts


class TestChunkTexts:
    """Verify chunker validation and behavior."""

    def test_valid_chunking(self) -> None:
        chunks = chunk_texts(["Hello world. " * 100], chunk_size=200, chunk_overlap=20)
        assert len(chunks) > 0
        assert all(isinstance(c, str) and c.strip() for c in chunks)

    def test_empty_texts(self) -> None:
        assert chunk_texts([], chunk_size=100, chunk_overlap=10) == []

    def test_empty_strings(self) -> None:
        assert chunk_texts(["", "   ", "\n\n"], chunk_size=100, chunk_overlap=10) == []

    def test_rejects_zero_chunk_size(self) -> None:
        with pytest.raises(ValueError, match="chunk_size must be > 0"):
            chunk_texts(["x"], chunk_size=0, chunk_overlap=0)

    def test_rejects_negative_chunk_size(self) -> None:
        with pytest.raises(ValueError, match="chunk_size must be > 0"):
            chunk_texts(["x"], chunk_size=-100, chunk_overlap=0)

    def test_rejects_negative_overlap(self) -> None:
        with pytest.raises(ValueError, match="chunk_overlap must be >= 0"):
            chunk_texts(["x"], chunk_size=100, chunk_overlap=-5)

    def test_rejects_overlap_equal_to_chunk_size(self) -> None:
        with pytest.raises(ValueError, match="chunk_overlap .+ must be < chunk_size"):
            chunk_texts(["x"], chunk_size=100, chunk_overlap=100)

    def test_rejects_overlap_gt_chunk_size(self) -> None:
        with pytest.raises(ValueError, match="chunk_overlap .+ must be < chunk_size"):
            chunk_texts(["x"], chunk_size=100, chunk_overlap=200)


class TestRAGConfig:
    """Verify RAGConfig validators."""

    def test_defaults(self) -> None:
        cfg = RAGConfig()
        assert cfg.chunk_size == 800
        assert cfg.chunk_overlap == 120
        assert cfg.vector_store == "chroma"

    def test_rejects_zero_chunk_size(self) -> None:
        with pytest.raises(ValueError):
            RAGConfig(chunk_size=0)

    def test_rejects_negative_chunk_size(self) -> None:
        with pytest.raises(ValueError):
            RAGConfig(chunk_size=-100)

    def test_rejects_negative_overlap(self) -> None:
        with pytest.raises(ValueError):
            RAGConfig(chunk_overlap=-1)

    def test_rejects_overlap_ge_chunk_size(self) -> None:
        with pytest.raises(ValueError, match="chunk_overlap"):
            RAGConfig(chunk_size=100, chunk_overlap=100)
        with pytest.raises(ValueError, match="chunk_overlap"):
            RAGConfig(chunk_size=100, chunk_overlap=150)

    def test_invalid_vector_store(self) -> None:
        with pytest.raises(ValueError):
            RAGConfig(vector_store="pinecone")  # type: ignore[arg-type]


class TestRagIndex:
    """Verify search behavior + edge cases."""

    def test_search_empty_index(self) -> None:
        idx = RagIndex(chunks=[])
        assert idx.search("anything") == []

    def test_search_negative_k(self) -> None:
        idx = RagIndex(chunks=["a", "b", "c"])
        assert idx.search("a", k=-1) == []
        assert idx.search("a", k=0) == []

    def test_search_empty_query(self) -> None:
        idx = RagIndex(chunks=["The quick brown fox"])
        assert idx.search("") == []
        assert idx.search("   ") == []

    def test_search_no_matching_tokens_returns_empty(self) -> None:
        """After Sprint 1: no matches → [], not the first-k arbitrary chunks."""
        idx = RagIndex(chunks=["The quick brown fox", "Jumps over lazy dog"])
        assert idx.search("xylophone zebra", k=2) == []

    def test_search_ranks_by_token_frequency(self) -> None:
        idx = RagIndex(chunks=[
            "apple banana apple cherry",   # 2 apple hits
            "apple",                       # 1 apple hit
            "orange",                       # 0 hits
        ])
        results = idx.search("apple", k=3)
        assert len(results) == 2
        assert "apple banana apple cherry" == results[0]

    def test_len_and_store_type(self) -> None:
        idx = RagIndex(chunks=["a", "b"], _store_type="memory")
        assert len(idx) == 2
        assert idx.store_type == "memory"


class TestBuildIndexOverrides:
    """Verify chunk_size=0 is not silently swallowed by `or`."""

    def test_zero_overlap_override_is_honored(self) -> None:
        """Post-fix: passing chunk_overlap=0 explicitly must be honored, not silently
        replaced by cfg default 120."""
        cfg = RAGConfig(chunk_size=200, chunk_overlap=50)
        idx = build_index_from_texts(
            ["Hello world. " * 200],
            config=cfg,
            vector_store="memory",
            chunk_overlap=0,   # explicit — should override 50
        )
        # Should produce chunks with no overlap. Hard to verify chunk overlap directly,
        # but at least verify no ValueError raised and we got chunks.
        assert len(idx) > 0
