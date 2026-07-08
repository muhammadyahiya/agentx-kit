"""Ready-to-run MCP tool templates: web search, TTS, knowledge research, database.

Import these directly (``pip install agentx-kit``) or let the scaffolder wire
them into a generated project's own MCP server. Each ``register_*`` function
adds one capability to a ``FastMCP`` instance; ``build_mcp_server`` assembles a
server from a selection of them by name::

    from agentx.tools.mcp_server import build_mcp_server

    mcp = build_mcp_server(name="my-tools", tools=["web_search", "database"])
    mcp.run()

Every tool degrades gracefully: missing optional dependencies or unreadable
inputs produce a diagnostic string/dict instead of raising, so an LLM caller
can recover instead of crashing the server.
"""
from __future__ import annotations

import logging
import re
import sqlite3
import tempfile
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

__all__ = [
    "AVAILABLE_MCP_TOOLS",
    "build_mcp_server",
    "run_mcp_server",
    "register_web_search",
    "register_tts",
    "register_knowledge_research",
    "register_database",
    "register_examples",
]

# Single source of truth for the wizard / connector / generator choices.
AVAILABLE_MCP_TOOLS = ("web_search", "tts", "knowledge_research", "database")

_READ_ONLY_SQL = re.compile(r"^\s*(SELECT|EXPLAIN|PRAGMA\s+table_info)\b", re.IGNORECASE)
_SQL_ROW_LIMIT = 200


def _require_fastmcp():
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "MCP tool templates need the MCP SDK. Install it with:\n"
            "    pip install 'agentx-kit[connector]'   # or: pip install fastmcp"
        ) from exc
    return FastMCP


# ──────────────────────────────────────────────────────────────────────────────
# Web search
# ──────────────────────────────────────────────────────────────────────────────

def register_web_search(mcp, max_results: int = 5) -> None:
    """Add ``web_search`` and ``fetch_url`` tools backed by ``agentx.tools.builtin``."""
    from .builtin import fetch_url as _fetch_url
    from .builtin import web_search as _web_search

    @mcp.tool()
    def web_search(query: str) -> str:
        """Search the public web (DuckDuckGo) and return titles, snippets, URLs."""
        return _web_search(query, max_results=max_results)

    @mcp.tool()
    def fetch_url(url: str) -> str:
        """Fetch an http(s) URL and return HTML-stripped plain text (size-capped)."""
        return _fetch_url(url)


# ──────────────────────────────────────────────────────────────────────────────
# Text-to-speech
# ──────────────────────────────────────────────────────────────────────────────

def register_tts(mcp, backend: str = "auto", output_dir: str | Path | None = None) -> None:
    """Add a ``text_to_speech`` tool backed by ``agentx.voice.tts.synthesize``.

    Audio is written to a file (not returned inline as base64) to keep tool
    responses small; the tool returns the file path plus backend/format.
    """
    out_dir = Path(output_dir) if output_dir else Path(tempfile.gettempdir()) / "agentx-tts"

    @mcp.tool()
    def text_to_speech(text: str, voice: str = "") -> dict:
        """Synthesize speech audio for ``text``; returns the saved audio file path.

        ``voice`` is backend-specific (e.g. "en-US-AriaNeural" for edge-tts);
        leave blank for the backend default. Requires one TTS backend to be
        installed (edge-tts, OpenAI, or pyttsx3) — see ``agentx-kit[voice]``.
        """
        from ..voice.tts import synthesize

        try:
            result = synthesize(text, backend=backend, voice=voice or None)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"tts-{abs(hash(text)) % 10**8}.{result.format}"
        out_path.write_bytes(result.audio)
        return {
            "ok": True,
            "file": str(out_path),
            "backend": result.backend,
            "format": result.format,
            "bytes": len(result.audio),
        }


# ──────────────────────────────────────────────────────────────────────────────
# Knowledge research (local document search — no embeddings required)
# ──────────────────────────────────────────────────────────────────────────────

def _score_chunk(query_terms: set[str], chunk: str) -> int:
    chunk_terms = set(re.findall(r"[a-z0-9]+", chunk.lower()))
    return len(query_terms & chunk_terms)


def _chunks_from_directory(root: Path) -> list[tuple[str, str]]:
    """Return ``[(source_filename, chunk_text), ...]`` for every doc under ``root``."""
    from ..rag.loaders import load_directory

    if not root.exists():
        return []
    try:
        docs = load_directory(root)
    except Exception as exc:  # noqa: BLE001
        logger.warning("knowledge_search: failed to load %s: %s", root, exc)
        return []

    chunks: list[tuple[str, str]] = []
    for filename, sections in docs.items():
        for section in sections:
            for para in re.split(r"\n\s*\n", section):
                para = para.strip()
                if len(para) >= 40:
                    chunks.append((filename, para))
    return chunks


def register_knowledge_research(mcp, root: str | Path = "./knowledge") -> None:
    """Add a ``knowledge_search`` tool: keyword search over local documents.

    Scans ``root`` (txt/md/pdf/docx/csv/xlsx) and ranks paragraph-sized chunks
    by term overlap with the query — zero-dependency, deterministic, no vector
    store required. For projects that already have a real RAG retriever, swap
    this tool's body for a call into that retriever instead.
    """
    root_path = Path(root)

    @mcp.tool()
    def knowledge_search(query: str, top_k: int = 5) -> str:
        """Search local knowledge-base documents and return the best-matching passages."""
        chunks = _chunks_from_directory(root_path)
        if not chunks:
            return f"No documents found under '{root_path}'. Add files there first."

        query_terms = set(re.findall(r"[a-z0-9]+", query.lower()))
        if not query_terms:
            return "Empty query."

        scored = sorted(
            ((source, text, _score_chunk(query_terms, text)) for source, text in chunks),
            key=lambda t: t[2],
            reverse=True,
        )
        top = [t for t in scored if t[2] > 0][:top_k]
        if not top:
            return f"No matches for '{query}' in {root_path}."
        return "\n\n".join(f"[{source}] {text}" for source, text, _ in top)


# ──────────────────────────────────────────────────────────────────────────────
# Database (read-only SQL)
# ──────────────────────────────────────────────────────────────────────────────

def register_database(mcp, db_path: str | Path = "./data.db") -> None:
    """Add a ``run_sql`` tool: read-only SQLite queries with a row cap.

    Only ``SELECT`` / ``EXPLAIN`` / ``PRAGMA table_info`` statements are
    allowed — anything else (INSERT/UPDATE/DELETE/DROP/ATTACH/…) is rejected
    before it reaches sqlite3. For Postgres/MySQL, replace the ``sqlite3.connect``
    call with your driver of choice; the guard/shape stay the same.
    """
    path = Path(db_path)

    @mcp.tool()
    def run_sql(query: str) -> dict:
        """Run a read-only SQL query against the project database; returns rows as JSON."""
        if not _READ_ONLY_SQL.match(query or ""):
            return {"ok": False, "error": "Only SELECT/EXPLAIN/PRAGMA table_info statements are allowed."}
        if not path.exists():
            return {"ok": False, "error": f"Database not found: {path}"}
        try:
            uri = f"file:{path}?mode=ro"
            conn = sqlite3.connect(uri, uri=True)
            conn.row_factory = sqlite3.Row
            try:
                cur = conn.execute(query)
                rows = [dict(r) for r in cur.fetchmany(_SQL_ROW_LIMIT)]
            finally:
                conn.close()
            return {"ok": True, "rows": rows, "row_count": len(rows), "truncated": len(rows) == _SQL_ROW_LIMIT}
        except sqlite3.Error as exc:
            return {"ok": False, "error": str(exc)}

    @mcp.tool()
    def list_tables() -> list[str]:
        """List table names in the project database."""
        if not path.exists():
            return []
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            return [r[0] for r in cur.fetchall()]
        finally:
            conn.close()


# ──────────────────────────────────────────────────────────────────────────────
# Example resource + prompt (shows the other two MCP primitives)
# ──────────────────────────────────────────────────────────────────────────────

def register_examples(mcp, app_name: str = "agentx-tools", app_version: str = "1.0") -> None:
    """Add one example resource and one example prompt, for reference."""

    @mcp.resource("config://app")
    def app_config() -> dict:
        """Read-only app metadata resource."""
        return {"name": app_name, "version": app_version}

    @mcp.prompt()
    def summarize(text: str) -> str:
        """Prompt template: ask the connected LLM to summarize ``text``."""
        return f"Summarize the following in 3-5 bullet points:\n\n{text}"


_REGISTRARS: dict[str, Callable] = {
    "web_search": register_web_search,
    "tts": register_tts,
    "knowledge_research": register_knowledge_research,
    "database": register_database,
}


def build_mcp_server(
    name: str = "agentx-tools",
    tools: list[str] | tuple[str, ...] = AVAILABLE_MCP_TOOLS,
    knowledge_root: str | Path = "./knowledge",
    db_path: str | Path = "./data.db",
    tts_backend: str = "auto",
    include_examples: bool = False,
):
    """Build a ``FastMCP`` server exposing the selected built-in tools.

    Args:
        name: Server name shown to MCP clients.
        tools: Subset of ``AVAILABLE_MCP_TOOLS`` to register.
        knowledge_root: Folder scanned by the ``knowledge_research`` tool.
        db_path: SQLite file queried by the ``database`` tool.
        tts_backend: Backend for the ``tts`` tool ("auto", "edge", "openai", "pyttsx3").
        include_examples: Also register the example resource + prompt.
    """
    FastMCP = _require_fastmcp()
    mcp = FastMCP(name)

    unknown = set(tools) - set(AVAILABLE_MCP_TOOLS)
    if unknown:
        raise ValueError(f"Unknown MCP tool(s) {sorted(unknown)}; choose from {AVAILABLE_MCP_TOOLS}")

    for tool_name in tools:
        if tool_name == "knowledge_research":
            register_knowledge_research(mcp, root=knowledge_root)
        elif tool_name == "database":
            register_database(mcp, db_path=db_path)
        elif tool_name == "tts":
            register_tts(mcp, backend=tts_backend)
        else:
            _REGISTRARS[tool_name](mcp)

    if include_examples:
        register_examples(mcp, app_name=name)

    return mcp


def run_mcp_server(**kwargs) -> None:
    """Build a server (see ``build_mcp_server`` for kwargs) and run it over stdio."""
    build_mcp_server(**kwargs).run()
