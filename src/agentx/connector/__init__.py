"""MCP connector — expose AgentX-Kit to Claude / Copilot / Codex.

`recommend_spec` and `build_project_from_statement` are pure (no MCP dep);
`build_server`/`run` require ``agentx-kit[connector]``.
"""
from .build import build_project_from_statement
from .recommend import recommend_spec

__all__ = ["recommend_spec", "build_project_from_statement", "build_server", "run", "client_config"]


def __getattr__(name: str):
    # Lazy: only import the MCP SDK when the server is actually requested.
    if name in ("build_server", "run", "client_config"):
        from . import server

        return getattr(server, name)
    raise AttributeError(name)
