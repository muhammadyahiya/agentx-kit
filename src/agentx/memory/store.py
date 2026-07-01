"""Two-tier agent memory — dependency-free, works with any framework.

* ``ConversationMemory`` — short-term, in-process windowed buffer of turns.
* ``LongTermMemory``    — append-only JSONL persisted per session, survives
                          restarts, with optional size-based rotation.
"""
from __future__ import annotations

import json
import os
import threading
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ConversationMemory:
    """A rolling window of the most recent (role, content) turns.

    Thread-safe: guarded by an internal lock so concurrent FastAPI requests
    don't lose turns.
    """

    def __init__(self, max_turns: int = 12):
        self.max_turns = max_turns
        self._turns: deque[tuple[str, str]] = deque(maxlen=max_turns)
        self._lock = threading.Lock()

    def add(self, role: str, content: str) -> None:
        with self._lock:
            self._turns.append((role, content))

    def add_user(self, content: str) -> None:
        self.add("user", content)

    def add_ai(self, content: str) -> None:
        self.add("assistant", content)

    def as_messages(self) -> list[dict]:
        """Return turns as chat-style message dicts."""
        with self._lock:
            return [{"role": r, "content": c} for r, c in self._turns]

    def transcript(self) -> str:
        with self._lock:
            return "\n".join(f"{r}: {c}" for r, c in self._turns)

    def clear(self) -> None:
        with self._lock:
            self._turns.clear()


class LongTermMemory:
    """Append-only JSONL memory keyed by session id.

    Supports:
      * Size-based rotation — when the log exceeds ``max_bytes`` it is renamed
        with a timestamp suffix and a fresh file is started.
      * Streaming reads — ``iter_history()`` reads line-by-line so the entire
        file never has to fit in memory.

    ``max_bytes=0`` disables rotation (default).
    """

    def __init__(self, path: str | Path, max_bytes: int = 0):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_bytes = int(max_bytes)

    def _maybe_rotate(self) -> None:
        if self.max_bytes <= 0 or not self.path.exists():
            return
        try:
            size = self.path.stat().st_size
        except OSError:
            return
        if size < self.max_bytes:
            return
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        rotated = self.path.with_name(f"{self.path.stem}.{stamp}{self.path.suffix}")
        try:
            os.replace(self.path, rotated)
        except OSError:
            pass  # Best-effort — next append creates a fresh file.

    def add(self, role: str, content: str, **meta) -> dict:
        event = {"ts": _now(), "role": role, "content": content, **meta}
        line = json.dumps(event) + "\n"
        with _lock:
            self._maybe_rotate()
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line)
        return event

    def iter_history(self) -> Iterator[dict]:
        """Yield events one-by-one — never loads the full file into memory.

        Preferred over ``history()`` for large logs.
        """
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue

    def history(self, limit: int | None = None) -> list[dict]:
        """Return the last ``limit`` events, or all events if ``limit`` is None.

        Uses ``iter_history`` under the hood — memory-efficient even for large
        files when ``limit`` is set.
        """
        if limit is not None and limit > 0:
            # Keep a bounded deque so memory usage is O(limit), not O(file_size).
            window: deque[dict] = deque(maxlen=limit)
            for event in self.iter_history():
                window.append(event)
            return list(window)
        return list(self.iter_history())

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()
