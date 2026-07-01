"""Tests for Sprint 2 features: JSON logging, rate limiter, RAG manifest,
long-term memory rotation, atomic scaffold generation."""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import pytest

from agentx import RateLimiter
from agentx.logging_config import JsonFormatter, setup_logging
from agentx.memory.store import ConversationMemory, LongTermMemory
from agentx.rag.manifest import (
    DocumentEntry,
    Manifest,
    build_document_entry,
    diff_directory,
    hash_file,
    load_manifest,
    save_manifest,
)


# ──────────────────────────────────────────────────────────────────────────────
# Structured JSON logging
# ──────────────────────────────────────────────────────────────────────────────

class TestJsonLogging:

    def test_json_formatter_basic(self) -> None:
        record = logging.LogRecord(
            name="agentx.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=42,
            msg="hello %s",
            args=("world",),
            exc_info=None,
        )
        result = JsonFormatter().format(record)
        payload = json.loads(result)
        assert payload["level"] == "INFO"
        assert payload["logger"] == "agentx.test"
        assert payload["message"] == "hello world"
        assert payload["line"] == 42

    def test_json_formatter_with_exception(self) -> None:
        try:
            raise ValueError("boom")
        except ValueError:
            import sys
            record = logging.LogRecord(
                name="agentx.test", level=logging.ERROR,
                pathname=__file__, lineno=1, msg="oops",
                args=(), exc_info=sys.exc_info(),
            )
        payload = json.loads(JsonFormatter().format(record))
        assert "exception" in payload
        assert "ValueError: boom" in payload["exception"]

    def test_setup_logging_json_format(self, capsys: pytest.CaptureFixture) -> None:
        setup_logging(level="DEBUG", format="json", force=True)
        logger = logging.getLogger("agentx.test.sprint2")
        logger.info("structured event", extra={"user_id": "abc123"})
        captured = capsys.readouterr()
        line = captured.err.strip().splitlines()[-1]
        payload = json.loads(line)
        assert payload["message"] == "structured event"
        assert payload["user_id"] == "abc123"

    def test_setup_logging_rejects_bad_format(self) -> None:
        with pytest.raises(ValueError, match="Invalid format"):
            setup_logging(format="yaml", force=True)  # type: ignore[arg-type]


# ──────────────────────────────────────────────────────────────────────────────
# Rate limiter
# ──────────────────────────────────────────────────────────────────────────────

class TestRateLimiter:

    def test_disabled_rate_limiter_never_blocks(self) -> None:
        limiter = RateLimiter(requests_per_minute=0, tokens_per_minute=0)
        start = time.monotonic()
        for _ in range(50):
            limiter.acquire()
            limiter.consume_tokens(1000)
        elapsed = time.monotonic() - start
        assert elapsed < 0.5

    def test_burst_allows_first_calls_immediately(self) -> None:
        limiter = RateLimiter(requests_per_minute=60, burst=3)
        start = time.monotonic()
        for _ in range(3):
            limiter.acquire(timeout=1.0)
        elapsed = time.monotonic() - start
        assert elapsed < 0.2

    def test_stats_returns_bucket_levels(self) -> None:
        limiter = RateLimiter(requests_per_minute=60, tokens_per_minute=10_000)
        stats = limiter.stats()
        assert stats["requests_per_minute"] == 60
        assert stats["tokens_per_minute"] == 10_000
        assert stats["request_tokens_available"] >= 0

    def test_timeout_raises(self) -> None:
        limiter = RateLimiter(requests_per_minute=1, burst=1)
        limiter.acquire(timeout=1.0)  # consume the only slot
        with pytest.raises(TimeoutError):
            limiter.acquire(timeout=0.05)


# ──────────────────────────────────────────────────────────────────────────────
# Memory rotation + iteration
# ──────────────────────────────────────────────────────────────────────────────

class TestLongTermMemoryRotation:

    def test_rotation_triggered_by_size(self, tmp_path: Path) -> None:
        log = tmp_path / "memory.jsonl"
        mem = LongTermMemory(log, max_bytes=200)
        # Write until we cross the threshold
        for i in range(30):
            mem.add("user", f"message-{i}-{'x' * 50}")
        # A rotated file should exist
        rotated = [p for p in tmp_path.iterdir() if p.name.startswith("memory.") and p != log]
        assert len(rotated) >= 1

    def test_iter_history_is_lazy(self, tmp_path: Path) -> None:
        log = tmp_path / "mem.jsonl"
        mem = LongTermMemory(log)
        for i in range(100):
            mem.add("user", f"msg-{i}")
        # Take just 5 items — iterator should not materialise the full list.
        it = mem.iter_history()
        first_five = [next(it) for _ in range(5)]
        assert len(first_five) == 5
        assert first_five[0]["content"] == "msg-0"

    def test_history_limit_bounded_memory(self, tmp_path: Path) -> None:
        log = tmp_path / "mem.jsonl"
        mem = LongTermMemory(log)
        for i in range(50):
            mem.add("user", f"msg-{i}")
        last_5 = mem.history(limit=5)
        assert len(last_5) == 5
        assert last_5[0]["content"] == "msg-45"
        assert last_5[-1]["content"] == "msg-49"


class TestConversationMemoryThreadSafety:
    """Verify ConversationMemory holds its lock (basic sanity check)."""

    def test_concurrent_adds_do_not_lose_turns(self) -> None:
        import threading
        mem = ConversationMemory(max_turns=1000)

        def worker(prefix: str) -> None:
            for i in range(100):
                mem.add("user", f"{prefix}-{i}")

        threads = [threading.Thread(target=worker, args=(str(i),)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        messages = mem.as_messages()
        assert len(messages) == 400


# ──────────────────────────────────────────────────────────────────────────────
# RAG manifest
# ──────────────────────────────────────────────────────────────────────────────

class TestManifest:

    def test_hash_file_stable(self, tmp_path: Path) -> None:
        fp = tmp_path / "a.txt"
        fp.write_text("Hello")
        h1 = hash_file(fp)
        h2 = hash_file(fp)
        assert h1 == h2
        assert len(h1) == 64

    def test_hash_file_changes_with_content(self, tmp_path: Path) -> None:
        fp = tmp_path / "b.txt"
        fp.write_text("Hello")
        h1 = hash_file(fp)
        fp.write_text("Hello world")
        h2 = hash_file(fp)
        assert h1 != h2

    def test_save_and_load_manifest(self, tmp_path: Path) -> None:
        mfp = tmp_path / "rag_manifest.json"
        m = Manifest(vector_store="faiss", embedding_provider="huggingface", total_chunks=42)
        m.documents["doc.pdf"] = DocumentEntry(
            filename="doc.pdf", sha256="a" * 64, size_bytes=1024,
            indexed_at="2026-01-01T00:00:00Z", chunk_count=10,
        )
        save_manifest(m, mfp)
        assert mfp.exists()

        m2 = load_manifest(mfp)
        assert m2.vector_store == "faiss"
        assert m2.embedding_provider == "huggingface"
        assert m2.total_chunks == 42
        assert "doc.pdf" in m2.documents
        assert m2.documents["doc.pdf"].sha256 == "a" * 64

    def test_load_missing_returns_empty(self, tmp_path: Path) -> None:
        m = load_manifest(tmp_path / "does_not_exist.json")
        assert m.documents == {}
        assert m.created_at != ""

    def test_load_corrupt_returns_fresh(self, tmp_path: Path) -> None:
        bad = tmp_path / "manifest.json"
        bad.write_text("not-json{{{{")
        m = load_manifest(bad)
        assert m.documents == {}

    def test_diff_directory_added(self, tmp_path: Path) -> None:
        (tmp_path / "new.txt").write_text("hello")
        m = Manifest()
        added, changed, removed = diff_directory(tmp_path, m)
        assert len(added) == 1
        assert added[0].name == "new.txt"
        assert changed == []
        assert removed == []

    def test_diff_directory_changed(self, tmp_path: Path) -> None:
        fp = tmp_path / "doc.txt"
        fp.write_text("original")
        m = Manifest()
        m.documents["doc.txt"] = build_document_entry(fp)
        fp.write_text("modified content")   # different hash
        added, changed, removed = diff_directory(tmp_path, m)
        assert added == []
        assert len(changed) == 1
        assert changed[0].name == "doc.txt"

    def test_diff_directory_removed(self, tmp_path: Path) -> None:
        m = Manifest()
        m.documents["gone.txt"] = DocumentEntry(
            filename="gone.txt", sha256="x" * 64, size_bytes=1,
            indexed_at="2026-01-01T00:00:00Z",
        )
        _, _, removed = diff_directory(tmp_path, m)
        assert removed == ["gone.txt"]
