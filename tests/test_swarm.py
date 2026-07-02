"""Tests for the swarm / sub-agent (agent-as-tool) module."""
from __future__ import annotations

import langgraph.prebuilt as lg_prebuilt

from agentx.swarm import SubAgentInput, make_subagent_tool


class _FakeAgent:
    """Stand-in for a compiled create_react_agent."""

    def __init__(self, reply: str):
        self._reply = reply

    async def ainvoke(self, state, config=None):
        from langchain_core.messages import AIMessage
        return {"messages": [AIMessage(content=self._reply)]}


def _patch(monkeypatch, reply="delegated answer"):
    monkeypatch.setattr("agentx.providers.get_chat_model", lambda *a, **k: object())
    monkeypatch.setattr(lg_prebuilt, "create_react_agent", lambda *a, **k: _FakeAgent(reply))


def test_subagent_tool_shape(monkeypatch):
    _patch(monkeypatch)
    tool = make_subagent_tool("researcher", "Delegate research tasks.")
    assert tool.name == "researcher"
    assert "Delegate research tasks." in tool.description
    assert list(tool.args.keys()) == ["task"]
    assert tool.args_schema is SubAgentInput


def test_subagent_sync_invoke(monkeypatch):
    _patch(monkeypatch, reply="42")
    tool = make_subagent_tool("calc", "Delegate math.")
    assert tool.invoke({"task": "6 times 7"}) == "42"


async def _ainvoke(tool, task):
    return await tool.ainvoke({"task": task})


def test_subagent_async_invoke(monkeypatch):
    import asyncio

    _patch(monkeypatch, reply="async answer")
    tool = make_subagent_tool("helper", "Delegate anything.")
    out = asyncio.new_event_loop().run_until_complete(_ainvoke(tool, "hi"))
    assert out == "async answer"


def test_subagent_empty_reply_fallback(monkeypatch):
    _patch(monkeypatch, reply="")
    tool = make_subagent_tool("q", "Delegate.")
    assert "no text" in tool.invoke({"task": "x"})


def test_subagent_error_is_caught(monkeypatch):
    monkeypatch.setattr("agentx.providers.get_chat_model", lambda *a, **k: object())

    class _Boom:
        async def ainvoke(self, *a, **k):
            raise RuntimeError("kaboom")

    monkeypatch.setattr(lg_prebuilt, "create_react_agent", lambda *a, **k: _Boom())
    tool = make_subagent_tool("x", "Delegate.")
    out = tool.invoke({"task": "t"})
    assert "error" in out.lower() and "kaboom" in out
