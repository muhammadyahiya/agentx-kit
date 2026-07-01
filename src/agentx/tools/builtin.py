"""Built-in tools usable by agents: keyless web search + safe URL fetch.

* ``web_search`` uses ``ddgs`` (DuckDuckGo) when available.
* ``fetch_url`` performs a safe GET with a size cap and HTML strip.

Both helpers are used by ``AutonomousAgent`` and ``ResearchAgent`` — extracted
here to keep the implementation in one place.
"""
from __future__ import annotations

import logging
import re
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)


def fetch_url(url: str, max_chars: int = 8000, timeout: int = 15) -> str:
    """Fetch ``url`` and return a plain-text (HTML-stripped) snippet.

    Args:
        url: HTTP/HTTPS URL to fetch.
        max_chars: Truncate the returned string to this many characters.
        timeout: Socket timeout in seconds.

    Only ``http://`` and ``https://`` URLs are honoured — attempts to use
    ``file://`` or other schemes are rejected.  Returns a diagnostic string on
    error rather than raising, so LLM tool-callers can recover gracefully.
    """
    if not url or not isinstance(url, str):
        return "fetch_url error: url must be a non-empty string"
    scheme = url.split(":", 1)[0].lower()
    if scheme not in ("http", "https"):
        return f"fetch_url error: only http/https URLs are allowed (got {scheme!r})"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "agentx-bot/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(65536).decode("utf-8", errors="replace")
        text = re.sub(r"<[^>]+>", " ", raw)
        text = re.sub(r"\s{2,}", " ", text).strip()
        return text[:max_chars]
    except urllib.error.HTTPError as exc:
        return f"fetch_url HTTP error: {exc.code} {exc.reason}"
    except urllib.error.URLError as exc:
        return f"fetch_url URL error: {exc.reason}"
    except Exception as exc:  # noqa: BLE001
        logger.warning("fetch_url unexpected error for %s: %s", url, exc)
        return f"fetch_url error: {exc}"


def web_search(query: str, max_results: int = 5) -> str:
    """Run a DuckDuckGo text search and return a formatted string."""
    try:
        from ddgs import DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS  # older package name
        except ImportError:
            return "Web search unavailable (install `ddgs`)."
    try:
        lines = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                title = r.get("title", "")
                body = r.get("body", "")
                url = r.get("href", r.get("url", ""))
                lines.append(f"- {title}\n  {body}\n  {url}")
        return "\n".join(lines) if lines else f"No results for '{query}'."
    except Exception as exc:  # noqa: BLE001
        logger.warning("web_search failed: %s", exc)
        return f"Web search error: {exc!r}"


def make_web_search_tool():
    """Return ``web_search`` wrapped as a LangChain ``@tool`` (lazy import)."""
    from langchain_core.tools import tool

    @tool
    def web_search_tool(query: str) -> str:
        """Search the public web for up-to-date information. Input a concise query."""
        return web_search(query)

    return web_search_tool
