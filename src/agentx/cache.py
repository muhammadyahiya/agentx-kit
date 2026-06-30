"""LLM response caching — cut cost & latency across all providers.

Caching is the top token-optimization lever (2026): repeat/near-repeat calls are
served from a local store instead of the model. This is an **exact** response
cache implemented as a LangChain ``BaseCache`` and installed globally, so every
``get_chat_model(...)`` call benefits automatically — no code changes.

    from agentx.cache import enable_caching, cache_stats
    enable_caching()                 # all subsequent LLM calls are cached
    ...
    print(cache_stats())             # hits, misses, est. tokens/$ saved

Persistence is a small SQLite file (default ``.agentx/llm_cache.sqlite``) with an
optional TTL. Stats track hit/miss and estimated tokens + USD saved (derived from
cached completion sizes — see ``agentx.insights.tokens``).
"""
from __future__ import annotations

import hashlib
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

_DEFAULT_PATH = ".agentx/llm_cache.sqlite"
_lock = threading.Lock()


def _key(prompt: str, llm_string: str) -> str:
    return hashlib.sha256(f"{llm_string}\x00{prompt}".encode("utf-8")).hexdigest()


def _model_from_llm_string(llm_string: str) -> str:
    # llm_string is a serialized model descriptor; best-effort model name for costing.
    for token in ("gpt-4o-mini", "gpt-4o", "gpt-4.1", "claude-3-5", "gemini-1.5", "llama"):
        if token in llm_string:
            return token
    return "gpt-4o-mini"


class AgentXCache:
    """A LangChain ``BaseCache`` backed by SQLite, with TTL + savings stats.

    Implements ``lookup``/``update`` (and ``aclear``) so it can be passed to
    ``langchain_core.globals.set_llm_cache``.
    """

    def __init__(self, path: str | Path = _DEFAULT_PATH, ttl: int | None = None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.ttl = ttl
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.path))

    def _init_db(self) -> None:
        with _lock, self._conn() as c:
            c.execute(
                "CREATE TABLE IF NOT EXISTS cache "
                "(key TEXT PRIMARY KEY, value TEXT, ts REAL, model TEXT, out_tokens INT)"
            )
            c.execute("CREATE TABLE IF NOT EXISTS stats (name TEXT PRIMARY KEY, val REAL)")
            for name in ("hits", "misses", "tokens_saved"):
                c.execute("INSERT OR IGNORE INTO stats(name, val) VALUES (?, 0)", (name,))

    def _bump(self, conn: sqlite3.Connection, name: str, by: float = 1) -> None:
        conn.execute("UPDATE stats SET val = val + ? WHERE name = ?", (by, name))

    # ----- BaseCache interface -----
    def lookup(self, prompt: str, llm_string: str) -> Any | None:
        import warnings

        from langchain_core.load import loads

        key = _key(prompt, llm_string)
        with _lock, self._conn() as c:
            row = c.execute("SELECT value, ts, out_tokens FROM cache WHERE key = ?", (key,)).fetchone()
            if not row:
                self._bump(c, "misses")
                return None
            value, ts, out_tokens = row
            if self.ttl is not None and (time.time() - ts) > self.ttl:
                c.execute("DELETE FROM cache WHERE key = ?", (key,))
                self._bump(c, "misses")
                return None
            self._bump(c, "hits")
            self._bump(c, "tokens_saved", out_tokens or 0)
        try:
            # We wrote these values ourselves, so deserialization is trusted.
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                return loads(value)
        except Exception:  # noqa: BLE001 - corrupt entry
            return None

    def update(self, prompt: str, llm_string: str, return_val: Any) -> None:
        from langchain_core.load import dumps

        from .insights.tokens import count_tokens

        key = _key(prompt, llm_string)
        model = _model_from_llm_string(llm_string)
        text = ""
        try:
            text = " ".join(getattr(g, "text", "") or "" for g in return_val)
        except Exception:  # noqa: BLE001
            text = ""
        out_tokens = count_tokens(text, model)
        try:
            payload = dumps(return_val)
        except Exception:  # noqa: BLE001 - non-serializable result; skip caching
            return
        with _lock, self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO cache(key, value, ts, model, out_tokens) VALUES (?, ?, ?, ?, ?)",
                (key, payload, time.time(), model, out_tokens),
            )

    def clear(self, **kwargs: Any) -> None:
        with _lock, self._conn() as c:
            c.execute("DELETE FROM cache")
            c.execute("UPDATE stats SET val = 0")

    def stats(self) -> dict:
        with _lock, self._conn() as c:
            rows = dict(c.execute("SELECT name, val FROM stats").fetchall())
            entries = c.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
        hits, misses = int(rows.get("hits", 0)), int(rows.get("misses", 0))
        total = hits + misses
        tokens_saved = int(rows.get("tokens_saved", 0))
        # Conservative blended estimate: $0.002 / 1K output tokens saved.
        cost_saved = round(tokens_saved / 1000 * 0.002, 6)
        return {
            "entries": entries,
            "hits": hits,
            "misses": misses,
            "hit_rate": round(hits / total, 3) if total else 0.0,
            "tokens_saved": tokens_saved,
            "est_usd_saved": cost_saved,
            "path": str(self.path),
        }


def enable_caching(path: str | Path = _DEFAULT_PATH, ttl: int | None = None) -> AgentXCache:
    """Install a global LLM response cache. All providers benefit automatically."""
    from langchain_core.globals import set_llm_cache

    cache = AgentXCache(path, ttl=ttl)
    set_llm_cache(cache)
    return cache


def disable_caching() -> None:
    from langchain_core.globals import set_llm_cache

    set_llm_cache(None)


def cache_stats(path: str | Path = _DEFAULT_PATH) -> dict:
    return AgentXCache(path).stats()


def clear_cache(path: str | Path = _DEFAULT_PATH) -> None:
    AgentXCache(path).clear()
