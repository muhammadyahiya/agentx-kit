"""Tools: MCP tool loading + a few built-in tools."""
from .builtin import fetch_url, make_web_search_tool, web_search
from .mcp import load_mcp_tools

__all__ = ["load_mcp_tools", "make_web_search_tool", "web_search", "fetch_url"]
