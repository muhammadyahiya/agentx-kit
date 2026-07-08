#!/usr/bin/env python
"""AgentX-Kit — MCP tool templates, standalone client demo.

Spawns ``mcp_toolkit_server.py`` over stdio, does a real MCP handshake, lists
every tool/resource/prompt it exposes, and calls each tool once — the same
flow any MCP client (Claude, a LangChain agent via ``load_mcp_tools``, or a
hand-rolled client) uses.

    pip install "agentx-kit[connector]"
    python examples/mcp_toolkit_client.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

_HERE = Path(__file__).parent


def _extract(result) -> str:
    """Pull text out of an MCP CallToolResult (structured or text content)."""
    structured = getattr(result, "structuredContent", None)
    if structured is not None:
        return json.dumps(structured, indent=2)
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            return text
    return str(result)


async def main() -> int:
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except ImportError:
        print("Install the connector extra first:  pip install 'agentx-kit[connector]'")
        return 1

    params = StdioServerParameters(command=sys.executable, args=[str(_HERE / "mcp_toolkit_server.py")])

    print("▶ connecting to mcp_toolkit_server.py over stdio …")
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("✓ connected. tools:", [t.name for t in tools.tools])

            print("\n▶ web_search('latest langgraph release')")
            print(_extract(await session.call_tool("web_search", {"query": "latest langgraph release"})))

            print("\n▶ knowledge_search('refund policy')  (./knowledge is empty by default — expected no-match)")
            print(_extract(await session.call_tool("knowledge_search", {"query": "refund policy"})))

            print("\n▶ list_tables()  (./data.db does not exist by default — expected empty)")
            print(_extract(await session.call_tool("list_tables", {})))

            print("\n▶ text_to_speech('Hello from AgentX-Kit')")
            print(_extract(await session.call_tool("text_to_speech", {"text": "Hello from AgentX-Kit"})))

            resources = await session.list_resources()
            print("\n▶ resources:", [str(r.uri) for r in resources.resources])
            prompts = await session.list_prompts()
            print("▶ prompts:", [p.name for p in prompts.prompts])

    print("\n✅ MCP tool templates work standalone. Point `knowledge_root`/`db_path` at real")
    print("   data, or generate a project with these tools baked in: `agentx new --mcp`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
