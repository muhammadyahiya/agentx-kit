"""Coerce JSON-in-content tool calls into structured ``tool_calls``.

Small / local models (llama3.2 and many Ollama models) frequently emit a tool
call as a JSON object in the message *content* — e.g. ``{"name": "web_search",
"parameters": {"query": "..."}}`` — instead of populating the structured
``tool_calls`` field the way OpenAI / Anthropic do. LangGraph's ``ToolNode`` /
``tools_condition`` only look at ``tool_calls``, so the call is never executed:
tools silently no-op and the raw JSON leaks to the user.

This module bridges that gap:

* :func:`coerce_message` rewrites such an ``AIMessage`` so its ``tool_calls`` is
  populated (keeping the same ``id`` so LangGraph's ``add_messages`` reducer
  *replaces* rather than appends).
* :func:`tool_call_coercion_hook` packages it as a ``create_react_agent``
  ``post_model_hook`` — drop it in and small models get working tool calls.

It is a no-op for models that already emit proper ``tool_calls``.
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Iterable

from langchain_core.messages import AIMessage

logger = logging.getLogger(__name__)

__all__ = ["coerce_message", "tool_call_coercion_hook", "parse_json_tool_call"]


def parse_json_tool_call(content: Any) -> tuple[str, dict] | None:
    """Parse ``content`` into ``(tool_name, args)`` if it is a JSON tool call.

    Tolerates Markdown code fences and the common ``parameters`` / ``arguments``
    / ``args`` key variants. Returns ``None`` when ``content`` is not a
    single JSON tool-call object.
    """
    if not isinstance(content, str):
        return None
    s = content.strip()
    # Strip a ```json … ``` (or bare ```) fence if present.
    if s.startswith("```"):
        s = s[3:]
        if s[:4].lower() == "json":
            s = s[4:]
        s = s.strip().rstrip("`").strip()
    if not (s.startswith("{") and s.endswith("}")):
        return None
    try:
        data = json.loads(s)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict) or "name" not in data:
        return None
    args = data.get("parameters", data.get("arguments", data.get("args", {})))
    # Some models double-encode the args as a JSON string.
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except (json.JSONDecodeError, ValueError):
            return None
    if not isinstance(args, dict):
        return None
    return str(data["name"]), args


def _resolve_name(name: str, tool_names: set[str]) -> str | None:
    """Match a model-provided name against known tools (exact, then fuzzy)."""
    if name in tool_names:
        return name
    lname = name.lower()
    for n in tool_names:
        if n.lower() == lname:
            return n
    # Prefix match either direction (models sometimes use a description prefix).
    for n in tool_names:
        if n.lower().startswith(lname[:20]) or lname.startswith(n.lower()):
            return n
    return None


def coerce_message(message: Any, tool_names: Iterable[str]) -> Any:
    """Return a copy of ``message`` with ``tool_calls`` populated if its content
    is a JSON tool call matching a known tool; otherwise return it unchanged.

    The returned message keeps the original ``id`` so LangGraph replaces the
    message in state instead of appending a duplicate.
    """
    if not isinstance(message, AIMessage) or message.tool_calls:
        return message
    parsed = parse_json_tool_call(message.content)
    if parsed is None:
        return message
    name, args = parsed
    resolved = _resolve_name(name, set(tool_names))
    if resolved is None:
        return message
    tool_call = {
        "name": resolved,
        "args": args,
        "id": f"call_{uuid.uuid4().hex[:8]}",
        "type": "tool_call",
    }
    return AIMessage(content="", tool_calls=[tool_call], id=message.id)


def tool_call_coercion_hook(tools: Iterable[Any]):
    """Build a ``create_react_agent`` ``post_model_hook`` that coerces
    JSON-in-content tool calls into structured ``tool_calls``.

    Usage::

        from agentx.tools import tool_call_coercion_hook
        agent = create_react_agent(
            llm, tools, prompt=system,
            post_model_hook=tool_call_coercion_hook(tools),
        )
    """
    names = {getattr(t, "name", "") for t in tools if getattr(t, "name", "")}

    def hook(state: dict) -> dict:
        messages = state.get("messages", [])
        if not messages:
            return {}
        last = messages[-1]
        coerced = coerce_message(last, names)
        if coerced is not last:
            logger.debug("coerced JSON-in-content into a structured tool_call")
            return {"messages": [coerced]}
        return {}

    return hook
