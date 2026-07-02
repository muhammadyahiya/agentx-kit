"""Tests for JSON-in-content tool-call coercion (agentx.tools.coerce)."""
from __future__ import annotations

from langchain_core.messages import AIMessage

from agentx.tools import coerce_message, load_mcp_tools, parse_json_tool_call, tool_call_coercion_hook


def test_parse_plain_json_call():
    assert parse_json_tool_call('{"name": "web_search", "parameters": {"query": "hi"}}') == (
        "web_search",
        {"query": "hi"},
    )


def test_parse_arguments_and_args_variants():
    assert parse_json_tool_call('{"name": "t", "arguments": {"a": 1}}') == ("t", {"a": 1})
    assert parse_json_tool_call('{"name": "t", "args": {"a": 1}}') == ("t", {"a": 1})


def test_parse_code_fenced_json():
    fenced = '```json\n{"name": "web_search", "parameters": {"query": "x"}}\n```'
    assert parse_json_tool_call(fenced) == ("web_search", {"query": "x"})


def test_parse_double_encoded_args():
    assert parse_json_tool_call('{"name": "t", "parameters": "{\\"q\\": 1}"}') == ("t", {"q": 1})


def test_parse_rejects_non_tool_json_and_prose():
    assert parse_json_tool_call('{"foo": "bar"}') is None
    assert parse_json_tool_call("Just a normal answer.") is None
    assert parse_json_tool_call('{"name": "t", "parameters": "not json"}') is None


def test_coerce_message_populates_tool_calls_and_keeps_id():
    msg = AIMessage(content='{"name": "web_search", "parameters": {"query": "hi"}}', id="abc")
    out = coerce_message(msg, {"web_search"})
    assert out is not msg
    assert out.id == "abc"  # same id → replaces in state
    assert len(out.tool_calls) == 1
    assert out.tool_calls[0]["name"] == "web_search"
    assert out.tool_calls[0]["args"] == {"query": "hi"}


def test_coerce_message_fuzzy_name_match():
    msg = AIMessage(content='{"name": "Search the web", "parameters": {"query": "hi"}}')
    out = coerce_message(msg, {"web_search"})
    # Description-style name does not match → left unchanged (no false tool call).
    assert out is msg


def test_coerce_message_noop_for_prose_and_structured():
    prose = AIMessage(content="Here is your answer.")
    assert coerce_message(prose, {"web_search"}) is prose

    structured = AIMessage(content="", tool_calls=[{"name": "web_search", "args": {}, "id": "1", "type": "tool_call"}])
    assert coerce_message(structured, {"web_search"}) is structured


def test_coerce_message_unknown_tool_left_alone():
    msg = AIMessage(content='{"name": "nonexistent", "parameters": {}}')
    assert coerce_message(msg, {"web_search"}) is msg


def test_hook_returns_replacement_update():
    hook = tool_call_coercion_hook([type("T", (), {"name": "web_search"})()])
    msg = AIMessage(content='{"name": "web_search", "parameters": {"query": "hi"}}', id="z")
    update = hook({"messages": [msg]})
    assert "messages" in update
    assert update["messages"][0].tool_calls[0]["name"] == "web_search"


def test_hook_noop_on_prose():
    hook = tool_call_coercion_hook([type("T", (), {"name": "web_search"})()])
    assert hook({"messages": [AIMessage(content="normal reply")]}) == {}
    assert hook({"messages": []}) == {}


def test_load_mcp_tools_safe_inside_running_loop():
    """Regression: load_mcp_tools must not raise when called from within a
    running event loop (lazy tool assembly inside an async graph node)."""
    import asyncio

    from agentx.tools import load_mcp_tools

    async def _inside_loop():
        # Empty config → returns [] fast, but must not raise a loop error even
        # though it is invoked from within a running loop.
        return load_mcp_tools({})

    assert asyncio.run(_inside_loop()) == []
