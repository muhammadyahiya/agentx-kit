"""Sub-agents / swarm — the *agent-as-tool* pattern.

A sub-agent is a full ReAct agent (with its own tools: web search, MCP servers,
retrievers, …) exposed to a *parent* agent as a single callable tool. The parent
delegates a task by "calling the tool"; the sub-agent runs to completion and
returns its answer. This is the standard, composable way to build swarms /
hierarchical multi-agent systems on top of LangGraph.

    from agentx.swarm import make_subagent_tool
    from agentx.tools import make_web_search_tool

    researcher = make_subagent_tool(
        name="researcher",
        description="Delegate web-research questions. Input a research task.",
        system_prompt="You are a meticulous web researcher. Cite sources.",
        tools=[make_web_search_tool()],
        provider="ollama", model="llama3.2",
    )

    # Attach to a parent agent like any other tool:
    parent = create_react_agent(llm, [researcher, ...])

Each sub-agent gets the JSON-in-content tool-call coercion hook, so it works
with small/local models too.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Sequence

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

__all__ = ["make_subagent_tool", "SubAgentInput"]


class SubAgentInput(BaseModel):
    """Input schema for a sub-agent tool."""

    task: str = Field(description="The task, question, or instruction to delegate to this sub-agent.")


def _last_text(messages: Sequence[Any]) -> str:
    for m in reversed(messages):
        content = getattr(m, "content", "")
        if content and isinstance(content, str):
            return content
    return ""


def make_subagent_tool(
    name: str,
    description: str,
    *,
    system_prompt: str = "",
    tools: Sequence[Any] | None = None,
    provider: str | None = None,
    model: str | None = None,
    recursion_limit: int = 12,
    temperature: float | None = None,
):
    """Build a LangChain tool that runs a ReAct sub-agent.

    Args:
        name: Tool name the parent agent will call (snake_case recommended).
        description: When the parent should delegate to this sub-agent. This is
            what the parent model reads to decide routing — be specific.
        system_prompt: The sub-agent's persona/instructions.
        tools: The sub-agent's own tools (web search, MCP tools, retrievers, …).
        provider / model: LLM for the sub-agent (defaults to project settings).
        recursion_limit: Max internal hops for the sub-agent per delegation.
        temperature: Optional sampling temperature override.

    Returns:
        A ``StructuredTool`` with both sync and async implementations.
    """
    from langchain_core.tools import StructuredTool

    sub_tools = list(tools or [])
    kwargs: dict = {}
    if temperature is not None:
        kwargs["temperature"] = temperature

    # Build the ReAct agent lazily on first delegation (never at import/build
    # time) so assembling a tool list can't spawn models, MCP sessions, or fail
    # on a missing provider dependency / API key.
    _cache: dict[str, object] = {}

    def _agent():
        if "agent" not in _cache:
            from langgraph.prebuilt import create_react_agent

            from ..providers import get_chat_model
            from ..tools import tool_call_coercion_hook

            llm = get_chat_model(provider, model, **kwargs)
            _cache["agent"] = create_react_agent(
                llm,
                sub_tools,
                prompt=system_prompt or f"You are {name}, a focused sub-agent. Complete the delegated task.",
                post_model_hook=tool_call_coercion_hook(sub_tools),
            )
        return _cache["agent"]

    async def _arun(task: str) -> str:
        try:
            result = await _agent().ainvoke(
                {"messages": [{"role": "user", "content": task}]},
                config={"recursion_limit": recursion_limit},
            )
            return _last_text(result.get("messages", [])) or "(sub-agent returned no text)"
        except Exception as exc:  # noqa: BLE001
            logger.exception("sub-agent %r failed", name)
            return f"Sub-agent '{name}' error: {exc}"

    _loop: list[asyncio.AbstractEventLoop | None] = [None]

    def _run(task: str) -> str:
        # If we're already inside a running event loop (e.g. the tool is being
        # executed synchronously by a parent agent's ToolNode during an async
        # graph run), we cannot call run_until_complete on it — run the coroutine
        # in a dedicated worker thread with its own loop instead.
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            running = False
        else:
            running = True
        if running:
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(lambda: asyncio.run(_arun(task))).result()
        # No running loop — reuse one private loop across calls so stateful async
        # tools (MCP) survive multiple delegations.
        if _loop[0] is None or _loop[0].is_closed():
            _loop[0] = asyncio.new_event_loop()
        return _loop[0].run_until_complete(_arun(task))

    return StructuredTool.from_function(
        func=_run,
        coroutine=_arun,
        name=name,
        description=description,
        args_schema=SubAgentInput,
    )
