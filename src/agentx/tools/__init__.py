"""Tools: MCP tool loading + a few built-in tools + tool-call coercion."""
from .builtin import fetch_url, make_web_search_tool, web_search
from .coerce import coerce_message, parse_json_tool_call, tool_call_coercion_hook
from .mcp import load_mcp_tools

__all__ = [
    "load_mcp_tools",
    "make_web_search_tool",
    "web_search",
    "fetch_url",
    "coerce_message",
    "parse_json_tool_call",
    "tool_call_coercion_hook",
]
