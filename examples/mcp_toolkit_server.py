#!/usr/bin/env python
"""AgentX-Kit — MCP tool templates, standalone server.

Exposes the built-in web search, TTS, knowledge research, and database tools
as an MCP server anyone can connect to — no generated project required.

    pip install "agentx-kit[connector,voice]"
    python examples/mcp_toolkit_server.py

Add it to an MCP client (Claude Desktop, Claude Code, Copilot, Codex):

    claude mcp add agentx-tools -- python examples/mcp_toolkit_server.py

Or drive it programmatically — see ``examples/mcp_toolkit_client.py``.
"""
from __future__ import annotations

from agentx.tools.mcp_server import build_mcp_server

mcp = build_mcp_server(
    name="agentx-tools",
    tools=["web_search", "tts", "knowledge_research", "database"],
    knowledge_root="./knowledge",   # drop .md/.txt/.pdf/.docx files here
    db_path="./data.db",            # any SQLite file (read-only queries)
    include_examples=True,          # config://app resource + summarize prompt
)

if __name__ == "__main__":
    mcp.run()
