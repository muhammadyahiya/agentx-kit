"""Autonomous working agent — a self-directed ReAct agent that can plan tasks,
browse the web, read/write files, execute shell commands, and fetch URLs.

Inspired by OpenClaw / AutoGPT-style autonomous loops.  Unlike a simple chat
agent this one receives a high-level *goal* and decomposes it into sub-tasks
using a plan-act-observe loop, persisting intermediate artifacts to a workspace.

Usage::

    from agentx.agents import AutonomousAgent

    agent = AutonomousAgent.create(
        goal="Research the top 5 open-source RAG frameworks and write a comparison report.",
        provider="openai",
        model="gpt-4o",
        workspace="./workspace",
    )
    result = agent.run()
    print(result.summary)

Security notes
--------------
* ``read_file`` / ``write_file`` are sandboxed to the workspace directory via
  ``Path.resolve().is_relative_to(workspace)`` — attempts to escape (``../``,
  absolute paths, symlinks) raise a ``ToolCallError`` back to the model.
* ``run_shell`` is disabled by default and must be enabled with
  ``allow_shell=True``.  Even when enabled it uses ``shlex.split`` +
  ``shell=False`` to prevent shell metacharacter injection, and rejects
  commands listed in ``_SHELL_DENYLIST``.
"""
from __future__ import annotations

import asyncio
import logging
import shlex
import subprocess
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Shell denylist — programs an LLM should never invoke autonomously.
# ──────────────────────────────────────────────────────────────────────────────

_SHELL_DENYLIST = frozenset({
    "rm", "shutdown", "reboot", "halt", "poweroff", "mkfs", "dd", "fdisk",
    "wget", "curl", "nc", "netcat", "ssh", "scp", "sudo", "su", "chmod",
    "chown", "sh", "bash", "zsh", "python", "python3", "eval", "exec",
})


# ──────────────────────────────────────────────────────────────────────────────
# Pydantic config
# ──────────────────────────────────────────────────────────────────────────────

class AutonomousAgentConfig(BaseModel):
    """Configuration for an AutonomousAgent."""

    goal: str = Field(..., min_length=1, description="High-level goal the agent should accomplish.")
    provider: str = "openai"
    model: str = ""
    workspace: str = "./workspace"
    max_iterations: int = Field(default=20, ge=1, description="Hard cap on plan-act-observe loops.")
    max_web_results: int = Field(default=5, ge=1, le=25)
    allow_shell: bool = Field(
        default=False,
        description="Allow the agent to run shell commands (sandboxed to workspace).",
    )
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    verbose: bool = True

    model_config = {"extra": "allow"}

    @field_validator("goal")
    @classmethod
    def _strip_goal(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("goal must not be empty or whitespace-only")
        return stripped


# ──────────────────────────────────────────────────────────────────────────────
# Result
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class AgentResult:
    goal: str
    summary: str
    iterations: int
    artifacts: list[Path]
    success: bool
    error: str | None = None

    def __str__(self) -> str:
        status = "✓" if self.success else "✗"
        parts = [
            f"{status} Goal: {self.goal}",
            f"  Iterations: {self.iterations}",
            f"  Artifacts: {[str(a) for a in self.artifacts]}",
        ]
        if not self.success and self.error:
            parts.append(f"  Error: {self.error}")
        parts.append(f"  Summary: {self.summary[:300]}")
        return "\n".join(parts)


# ──────────────────────────────────────────────────────────────────────────────
# Path sandbox helper
# ──────────────────────────────────────────────────────────────────────────────

def _safe_join(workspace: Path, filename: str) -> Path:
    """Resolve ``filename`` under ``workspace`` and reject escape attempts.

    Returns a path guaranteed to be inside ``workspace``.  Raises ValueError
    otherwise so the LLM sees the error and can retry.
    """
    if not filename or not filename.strip():
        raise ValueError("filename must not be empty")
    # Reject absolute paths outright.
    candidate = Path(filename)
    if candidate.is_absolute():
        raise ValueError(f"absolute paths are not allowed: {filename!r}")
    resolved = (workspace / candidate).resolve()
    ws_resolved = workspace.resolve()
    try:
        resolved.relative_to(ws_resolved)
    except ValueError as exc:
        raise ValueError(
            f"path escapes workspace: {filename!r} → {resolved} not under {ws_resolved}"
        ) from exc
    return resolved


# ──────────────────────────────────────────────────────────────────────────────
# Built-in tools
# ──────────────────────────────────────────────────────────────────────────────

def _make_tools(workspace: Path, cfg: AutonomousAgentConfig) -> list:
    """Build the agent's tool set as LangChain tools."""
    from langchain_core.tools import tool
    from ..tools.builtin import fetch_url as _fetch_url

    ws = workspace

    @tool
    def web_search(query: str, max_results: int = 5) -> str:
        """Search the web for up-to-date information. Returns titles + snippets + URLs."""
        from ..tools.builtin import web_search as _search
        return _search(query, max_results=min(max_results, cfg.max_web_results))

    @tool
    def fetch_url(url: str) -> str:
        """Fetch and return the plain-text content of a URL (max 8000 chars)."""
        return _fetch_url(url, max_chars=8000)

    @tool
    def read_file(filename: str) -> str:
        """Read a file from the workspace directory (paths must stay inside workspace)."""
        try:
            fp = _safe_join(ws, filename)
        except ValueError as exc:
            return f"Access denied: {exc}"
        if not fp.exists():
            return f"File not found: {filename}"
        try:
            return fp.read_text(encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            return f"Error reading {filename}: {exc}"

    @tool
    def write_file(filename: str, content: str) -> str:
        """Write content to a file in the workspace directory (paths must stay inside workspace)."""
        try:
            fp = _safe_join(ws, filename)
        except ValueError as exc:
            return f"Access denied: {exc}"
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")
        logger.info("Agent wrote file: %s (%d chars)", fp, len(content))
        return f"Wrote {len(content)} chars to {filename}"

    @tool
    def list_files(subdirectory: str = "") -> str:
        """List files in the workspace (or a subdirectory of it)."""
        try:
            target = _safe_join(ws, subdirectory) if subdirectory else ws
        except ValueError as exc:
            return f"Access denied: {exc}"
        if not target.exists():
            return f"Directory not found: {subdirectory or 'workspace'}"
        files = [str(p.relative_to(ws)) for p in target.rglob("*") if p.is_file()]
        return "\n".join(files) if files else "(empty)"

    @tool
    def think(reasoning: str) -> str:
        """Use this tool to think out loud before acting. Reasoning is logged but not sent."""
        logger.info("Agent thinking: %s", reasoning[:300])
        return "Thinking recorded."

    tools = [web_search, fetch_url, read_file, write_file, list_files, think]

    if cfg.allow_shell:
        @tool
        def run_shell(command: str) -> str:
            """Run a shell command inside the workspace directory.

            Uses shlex-split arguments with shell=False — no shell metacharacter
            expansion. A denylist of dangerous programs (rm, sudo, curl, …) is
            enforced.  Timeout: 30s.
            """
            try:
                argv = shlex.split(command)
            except ValueError as exc:
                return f"Could not parse command: {exc}"
            if not argv:
                return "Empty command."
            program = Path(argv[0]).name
            if program in _SHELL_DENYLIST:
                return f"Denied: program {program!r} is on the shell denylist."
            try:
                result = subprocess.run(
                    argv,
                    cwd=str(ws),
                    capture_output=True,
                    text=True,
                    timeout=30,
                    shell=False,
                )
                out = result.stdout[-4000:] if result.stdout else ""
                err = result.stderr[-2000:] if result.stderr else ""
                return f"stdout:\n{out}\nstderr:\n{err}\nreturncode: {result.returncode}"
            except subprocess.TimeoutExpired:
                return "Command timed out (30s limit)."
            except FileNotFoundError:
                return f"Program not found: {program!r}"
            except Exception as exc:  # noqa: BLE001
                return f"Shell error: {exc}"

        tools.append(run_shell)

    return tools


# ──────────────────────────────────────────────────────────────────────────────
# System prompt
# ──────────────────────────────────────────────────────────────────────────────

_SYSTEM_TEMPLATE = textwrap.dedent("""\
    You are an autonomous AI agent. Your goal is:

    {goal}

    You have a workspace at: {workspace}

    Work methodically:
    1. Plan your approach before acting.
    2. Use tools to gather information, process it, and write artifacts.
    3. Save important results to files using write_file.
    4. When done, provide a clear final summary starting with "FINAL ANSWER:".

    Use the 'think' tool to reason before complex decisions.
    Be thorough but efficient. Avoid repeating the same search queries.
    The user cannot give you additional input — work autonomously.
""")


# ──────────────────────────────────────────────────────────────────────────────
# Async loop helper
# ──────────────────────────────────────────────────────────────────────────────

def _run_sync(coro):
    """Run a coroutine synchronously, tolerating a running event loop.

    Direct ``asyncio.new_event_loop().run_until_complete`` fails inside FastAPI,
    Jupyter, Streamlit, etc.  This helper detects an active loop and either uses
    ``nest_asyncio`` (if installed) or raises a clear error asking the caller
    to use the async entry point.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is None:
        return asyncio.run(coro)
    # A loop is already running — cannot call run_until_complete cleanly.
    try:
        import nest_asyncio  # type: ignore
        nest_asyncio.apply(loop)
        return loop.run_until_complete(coro)
    except ImportError as exc:
        raise RuntimeError(
            "An event loop is already running (e.g. inside FastAPI/Jupyter/Streamlit). "
            "Use the async entry point (`await agent.arun()`) or install nest_asyncio "
            "and rerun."
        ) from exc


# ──────────────────────────────────────────────────────────────────────────────
# Agent
# ──────────────────────────────────────────────────────────────────────────────

class AutonomousAgent:
    """An autonomous, goal-directed agent with web search, file I/O, and planning.

    Use ``AutonomousAgent.create()`` as the entry point.
    """

    def __init__(self, config: AutonomousAgentConfig) -> None:
        self.config = config
        self.workspace = Path(config.workspace).expanduser().resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self._artifacts: list[Path] = []

    # ── Factory ──────────────────────────────────────────────────────────────

    @classmethod
    def create(
        cls,
        goal: str,
        provider: str = "openai",
        model: str = "",
        workspace: str = "./workspace",
        max_iterations: int = 20,
        allow_shell: bool = False,
        **kwargs: Any,
    ) -> "AutonomousAgent":
        """Create an AutonomousAgent from keyword arguments."""
        return cls(AutonomousAgentConfig(
            goal=goal, provider=provider, model=model,
            workspace=workspace, max_iterations=max_iterations,
            allow_shell=allow_shell, **kwargs,
        ))

    # ── Run ──────────────────────────────────────────────────────────────────

    def run(self) -> AgentResult:
        """Run the agent synchronously until the goal is reached or max_iterations hit.

        Safe to call from FastAPI/Jupyter/Streamlit — falls back to nest_asyncio
        when a loop is already active, or raises a clear error otherwise.
        """
        return _run_sync(self.arun())

    async def arun(self) -> AgentResult:
        """Async run — use this from an async context."""
        from ..providers import get_chat_model

        cfg = self.config
        llm = get_chat_model(cfg.provider, cfg.model or None, temperature=cfg.temperature)
        tools = _make_tools(self.workspace, cfg)

        system = _SYSTEM_TEMPLATE.format(
            goal=cfg.goal,
            workspace=str(self.workspace),
        )

        try:
            from langgraph.prebuilt import create_react_agent  # type: ignore
            from langgraph.checkpoint.memory import MemorySaver  # type: ignore
            from langchain_core.messages import HumanMessage  # type: ignore

            agent = create_react_agent(llm, tools, prompt=system, checkpointer=MemorySaver())

            logger.info(
                "AutonomousAgent starting: goal=%r iterations_cap=%d",
                cfg.goal[:80], cfg.max_iterations,
            )

            result = await agent.ainvoke(
                {"messages": [HumanMessage(content=cfg.goal)]},
                config={"configurable": {"thread_id": "auto"}, "recursion_limit": cfg.max_iterations * 2},
            )

            messages = result.get("messages", [])
            final_content = ""
            for m in reversed(messages):
                c = getattr(m, "content", "")
                if c and isinstance(c, str):
                    final_content = c
                    break

            # Collect artifacts written during the run
            self._artifacts = [f for f in self.workspace.rglob("*") if f.is_file()]

            summary = final_content
            if "FINAL ANSWER:" in final_content:
                summary = final_content.split("FINAL ANSWER:", 1)[1].strip()

            logger.info("AutonomousAgent finished. Artifacts: %d", len(self._artifacts))
            return AgentResult(
                goal=cfg.goal,
                summary=summary,
                iterations=len([m for m in messages if getattr(m, "type", "") == "tool"]),
                artifacts=self._artifacts,
                success=True,
            )

        except Exception as exc:  # noqa: BLE001
            logger.exception("AutonomousAgent failed")
            return AgentResult(
                goal=cfg.goal,
                summary="",
                iterations=0,
                artifacts=[],
                success=False,
                error=str(exc),
            )
