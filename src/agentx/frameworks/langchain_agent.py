"""LangGraph agent adapter.

``build_react_agent`` wires a provider-agnostic chat model (from our factory) +
tools + an optional system prompt into a LangGraph ReAct agent. Requires
``agentx-kit[langgraph]`` plus the chosen provider extra.
"""
from __future__ import annotations

from typing import Any

from ..providers import get_chat_model


def build_react_agent(
    provider: str | None = None,
    model: str | None = None,
    tools: list[Any] | None = None,
    system_prompt: str | None = None,
    **model_kwargs: Any,
):
    """Return a compiled LangGraph ReAct agent (a runnable)."""
    try:
        from langgraph.prebuilt import create_react_agent
    except ImportError as exc:
        raise ImportError(
            "LangGraph is required. Install with: uv pip install 'agentx-kit[langgraph]'"
        ) from exc

    llm = get_chat_model(provider, model, **model_kwargs)
    tools = tools or []
    if system_prompt:
        return create_react_agent(llm, tools, prompt=system_prompt)
    return create_react_agent(llm, tools)


def run_agent(agent, user_input: str) -> str:
    """Invoke a LangGraph agent with a single user message; return final text."""
    result = agent.invoke({"messages": [{"role": "user", "content": user_input}]})
    messages = result.get("messages", []) if isinstance(result, dict) else []
    if messages:
        last = messages[-1]
        return getattr(last, "content", None) or (last.get("content", "") if isinstance(last, dict) else "")
    return str(result)
