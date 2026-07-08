"""Tests for the agentx.tools.mcp_server tool templates (web search, tts, knowledge, db)."""
import asyncio
import json
import sqlite3

import pytest

mcp_sdk = pytest.importorskip("mcp", reason="MCP SDK not installed (pip install 'agentx-kit[connector]')")

from agentx.tools.mcp_server import (  # noqa: E402
    AVAILABLE_MCP_TOOLS,
    build_mcp_server,
    register_database,
    register_knowledge_research,
)


def _tool_names(mcp) -> set[str]:
    import asyncio

    async def _list():
        tools = await mcp.list_tools()
        return {t.name for t in tools}

    return asyncio.run(_list())


def test_build_mcp_server_registers_selected_tools():
    mcp = build_mcp_server(name="t", tools=["web_search"])
    assert _tool_names(mcp) == {"web_search", "fetch_url"}


def test_build_mcp_server_rejects_unknown_tool():
    with pytest.raises(ValueError):
        build_mcp_server(tools=["not-a-tool"])


def test_build_mcp_server_all_tools_registers_everything():
    mcp = build_mcp_server(name="t", tools=list(AVAILABLE_MCP_TOOLS))
    names = _tool_names(mcp)
    for expected in ("web_search", "fetch_url", "text_to_speech", "knowledge_search", "run_sql", "list_tables"):
        assert expected in names


def _call(mcp, name, args):
    result = asyncio.run(mcp.call_tool(name, args))
    content = result[0] if isinstance(result, tuple) else result
    return content[0].text


def test_database_tool_rejects_write_queries(tmp_path):
    db_path = tmp_path / "t.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE items(id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO items(name) VALUES ('widget')")
    conn.commit()
    conn.close()

    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("db-test")
    register_database(mcp, db_path=db_path)

    ok_result = json.loads(_call(mcp, "run_sql", {"query": "SELECT * FROM items"}))
    assert ok_result["ok"] is True
    assert ok_result["rows"] == [{"id": 1, "name": "widget"}]

    rejected = json.loads(_call(mcp, "run_sql", {"query": "DROP TABLE items"}))
    assert rejected["ok"] is False

    tables = _call(mcp, "list_tables", {})
    assert "items" in tables


def test_knowledge_search_finds_matching_paragraph(tmp_path):
    docs = tmp_path / "knowledge"
    docs.mkdir()
    (docs / "policy.md").write_text(
        "# Refunds\n\nCustomers get a refund within 30 days of purchase.\n\n"
        "# Shipping\n\nOrders ship within two business days.\n"
    )

    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("kb-test")
    register_knowledge_research(mcp, root=docs)

    text = _call(mcp, "knowledge_search", {"query": "refund", "top_k": 3})
    assert "refund" in text.lower()


def test_knowledge_search_empty_dir_returns_message(tmp_path):
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("kb-empty")
    register_knowledge_research(mcp, root=tmp_path / "does-not-exist")

    text = _call(mcp, "knowledge_search", {"query": "anything", "top_k": 3})
    assert "No documents found" in text
