"""Load MCP servers as LangChain tools via ``langchain-mcp-adapters``.

Config format (JSON or dict) follows MultiServerMCPClient, e.g.::

    {
      "filesystem": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path"],
        "transport": "stdio"
      }
    }

Returns ``[]`` (never raises) if the extra isn't installed or loading fails, so
agents degrade gracefully.
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _load_config(config: str | Path | dict | None) -> dict:
    if config is None:
        return {}
    if isinstance(config, dict):
        return config
    p = Path(config)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def load_mcp_tools(config: str | Path | dict | None) -> list[Any]:
    """Synchronously load MCP tools from a config path/dict. Returns [] on failure."""
    servers = _load_config(config)
    if not servers:
        return []
    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
    except ImportError:
        logger.warning("langchain-mcp-adapters not installed; run `uv pip install 'agentx-kit[mcp]'`.")
        return []

    async def _gather() -> list[Any]:
        client = MultiServerMCPClient(servers)
        return await client.get_tools()

    try:
        return asyncio.run(_gather())
    except RuntimeError:
        # Already inside an event loop (e.g. notebook) — run in a fresh loop.
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_gather())
        finally:
            loop.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to load MCP tools: %s", exc)
        return []
