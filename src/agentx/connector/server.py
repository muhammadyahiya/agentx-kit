"""MCP server exposing AgentX-Kit to Claude / Copilot / Codex as a connector.

Run over stdio with ``agentx mcp``. Any MCP-capable client (Claude Desktop,
Claude Code, GitHub Copilot, OpenAI Codex) can then, from a single prompt with a
problem statement, generate a complete, ready-to-run agent project.

Tools:
  • recommend_project(problem_statement)         → suggested stack + features
  • create_agent_project(problem_statement, …)   → generates the project, returns files
  • list_providers()                             → supported LLM providers
  • analyze_prompt(prompt) / optimize_prompt(…)  → prompt insights
"""
from __future__ import annotations

from typing import Any

from ..providers import all_specs
from .build import build_project_from_statement
from .recommend import recommend_spec


def build_server():
    """Construct the FastMCP server. Requires ``agentx-kit[connector]``."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "The MCP connector needs the MCP SDK. Install it with:\n"
            "    pip install 'agentx-kit[connector]'"
        ) from exc

    mcp = FastMCP("agentx-kit")

    @mcp.tool()
    def list_providers() -> list[dict]:
        """List the LLM providers AgentX-Kit can target and the env vars each needs."""
        return [
            {"id": s.id, "label": s.label, "default_model": s.default_model, "env_vars": list(s.env_vars)}
            for s in all_specs()
        ]

    @mcp.tool()
    def recommend_project(problem_statement: str) -> dict:
        """Recommend a framework, provider, agent count and features for a use case.

        Call this first to preview the stack; then call create_agent_project.
        """
        return recommend_spec(problem_statement)

    @mcp.tool()
    def create_agent_project(
        problem_statement: str,
        name: str = "",
        framework: str = "",
        provider: str = "",
        model: str = "",
        agents: int = 0,
        features: list[str] | None = None,
        mcp_tools: list[str] | None = None,
        enterprise: bool = False,
        output_dir: str = "",
    ) -> dict:
        """Generate a complete, runnable agent project from a problem statement.

        Leave optional args blank to let AgentX infer them from the problem
        statement. ``features`` may include: rag, memory, mcp, skills,
        observability, guardrails, serve, docker, ci, evals. When ``mcp`` is
        in ``features`` (or inferred), the project gets its own MCP server;
        ``mcp_tools`` selects which built-in tools it exposes — any subset of
        web_search, tts, knowledge_research, database (blank = inferred from
        the problem statement, or all four). Set ``enterprise`` true for the
        full production pack. Returns the target dir, file tree, key file
        contents, and run steps.
        """
        try:
            return build_project_from_statement(
                problem_statement, name=name, framework=framework, provider=provider,
                model=model, agents=agents, features=features, mcp_tools=mcp_tools,
                enterprise=enterprise, output_dir=output_dir, create_venv=False, overwrite=True,
            )
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    @mcp.tool()
    def analyze_prompt(prompt: str, model: str = "gpt-4o-mini") -> dict:
        """Analyse a prompt: token count, quality score (0-100), suggestions, warnings."""
        from ..insights import analyze_prompt as _analyze

        a = _analyze(prompt, model)
        return {
            "tokens": a.tokens, "quality_score": a.quality_score,
            "checks": a.checks, "suggestions": a.suggestions, "warnings": a.warnings,
        }

    @mcp.tool()
    def optimize_prompt(prompt: str, provider: str = "openai", model: str = "", feedback: str = "") -> dict:
        """Refine a prompt with an LLM (preserving intent); returns improved prompt + rationale."""
        from ..insights import optimize_prompt as _optimize

        r = _optimize(prompt, provider, model or None, feedback=feedback)
        return {"ok": r.ok, "improved": r.improved, "rationale": r.rationale, "error": r.error}

    return mcp


def run() -> None:
    """Run the MCP server over stdio (for Claude/Copilot/Codex)."""
    build_server().run()


def client_config(command: str = "agentx") -> dict[str, Any]:
    """Return an MCP client config snippet for this server."""
    return {"mcpServers": {"agentx-kit": {"command": command, "args": ["mcp"]}}}
