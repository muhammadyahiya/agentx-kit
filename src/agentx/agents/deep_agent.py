"""Deep-agent building blocks — the same primitives behind LangChain's
``deepagents`` harness and Claude Code's own coding harness:

1. **Planning** — a no-op ``write_todos`` tool. Forcing the model to keep an
   explicit, visible task list measurably improves coherence on long-running
   work, even though the tool does nothing but record state.
2. **Filesystem** — sandboxed ``read_file``/``write_file``/``edit_file``/
   ``list_files`` tools scoped to a workspace directory, for context
   offloading (write intermediate results to disk instead of the transcript).
3. **Sub-agent delegation** — a single ``task`` dispatcher tool that routes to
   named specialist sub-agents (agent-as-tool, isolated context per call), the
   same shape as Claude Code's ``Task`` tool.
4. **Reflection** — an optional critic pass that reviews the draft answer and
   asks for revisions before returning, bounded by ``max_revisions``.
5. **Compaction** — summarise older messages once the transcript grows past a
   token budget, keeping the most recent turns verbatim.

Use the pieces directly to build a custom LangGraph node, or use ``DeepAgent``
for a standalone, goal-directed run::

    from agentx.agents import DeepAgent, SubAgentSpec

    agent = DeepAgent.create(
        goal="Audit this repo's error handling and write a report.",
        provider="openai",
        workspace="./workspace",
        subagents=[
            SubAgentSpec(name="reviewer", description="Reviews code for bugs.",
                         prompt="You are a meticulous code reviewer."),
        ],
        reflection=ReflectionConfig(enabled=True, max_revisions=2),
    )
    result = agent.run()
    print(result.summary)
"""
from __future__ import annotations

import logging
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Sequence

from pydantic import BaseModel, Field

from ._workspace import safe_join

logger = logging.getLogger(__name__)

__all__ = [
    "Todo",
    "make_planning_tool",
    "make_filesystem_tools",
    "SubAgentSpec",
    "build_subagent_dispatcher",
    "ReflectionConfig",
    "run_with_reflection",
    "compact_messages",
    "DeepAgentConfig",
    "DeepAgentResult",
    "DeepAgent",
]

TodoStatus = Literal["pending", "in_progress", "completed"]


class Todo(BaseModel):
    """A single planned task, tracked by the ``write_todos`` planning tool."""

    content: str
    status: TodoStatus = "pending"


# ──────────────────────────────────────────────────────────────────────────────
# 1. Planning
# ──────────────────────────────────────────────────────────────────────────────

def make_planning_tool():
    """Build the ``write_todos`` no-op planning tool.

    Returns ``(tool, box)`` where ``box["todos"]`` always holds the most
    recently submitted task list — inspect it after a run to see the agent's
    final plan state.
    """
    from langchain_core.tools import StructuredTool

    box: dict[str, list[Todo]] = {"todos": []}

    class WriteTodosInput(BaseModel):
        todos: list[Todo] = Field(description="The full, updated task list (replaces the previous one).")

    def _write(todos: list[Todo]) -> str:
        box["todos"] = list(todos)
        done = sum(1 for t in todos if t.status == "completed")
        return f"Todo list updated ({done}/{len(todos)} completed)."

    tool = StructuredTool.from_function(
        func=_write,
        name="write_todos",
        description=(
            "Record or update your task plan. Call this before starting work and "
            "after completing each step. Submit the FULL list every time with each "
            "task's current status (pending, in_progress, completed)."
        ),
        args_schema=WriteTodosInput,
    )
    return tool, box


# ──────────────────────────────────────────────────────────────────────────────
# 2. Filesystem
# ──────────────────────────────────────────────────────────────────────────────

def make_filesystem_tools(workspace: str | Path) -> list:
    """Build sandboxed ``read_file``/``write_file``/``edit_file``/``list_files``
    tools scoped to ``workspace`` (created if missing). Paths cannot escape it.
    """
    from langchain_core.tools import tool

    ws = Path(workspace).expanduser().resolve()
    ws.mkdir(parents=True, exist_ok=True)

    @tool
    def read_file(filename: str) -> str:
        """Read a file from the agent's workspace (paths must stay inside it)."""
        try:
            fp = safe_join(ws, filename)
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
        """Write content to a file in the agent's workspace (paths must stay inside it)."""
        try:
            fp = safe_join(ws, filename)
        except ValueError as exc:
            return f"Access denied: {exc}"
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} chars to {filename}"

    @tool
    def edit_file(filename: str, old_text: str, new_text: str) -> str:
        """Replace the first occurrence of old_text with new_text in a workspace file."""
        try:
            fp = safe_join(ws, filename)
        except ValueError as exc:
            return f"Access denied: {exc}"
        if not fp.exists():
            return f"File not found: {filename}"
        content = fp.read_text(encoding="utf-8")
        if old_text not in content:
            return f"old_text not found in {filename}"
        fp.write_text(content.replace(old_text, new_text, 1), encoding="utf-8")
        return f"Edited {filename}"

    @tool
    def list_files(subdirectory: str = "") -> str:
        """List files in the agent's workspace (or a subdirectory of it)."""
        try:
            target = safe_join(ws, subdirectory) if subdirectory else ws
        except ValueError as exc:
            return f"Access denied: {exc}"
        if not target.exists():
            return f"Directory not found: {subdirectory or 'workspace'}"
        files = [str(p.relative_to(ws)) for p in target.rglob("*") if p.is_file()]
        return "\n".join(files) if files else "(empty)"

    return [read_file, write_file, edit_file, list_files]


# ──────────────────────────────────────────────────────────────────────────────
# 3. Sub-agent delegation
# ──────────────────────────────────────────────────────────────────────────────

class SubAgentSpec(BaseModel):
    """Describes one specialist sub-agent available to a deep agent's dispatcher."""

    name: str
    description: str = Field(description="When the parent should delegate to this sub-agent.")
    prompt: str = ""
    tools: list[Any] = Field(default_factory=list)
    provider: str | None = None
    model: str | None = None

    model_config = {"arbitrary_types_allowed": True}


def build_subagent_dispatcher(specs: Sequence[SubAgentSpec], *, recursion_limit: int = 12):
    """Build a single ``task`` tool that dispatches to a named sub-agent.

    This is the "agent-as-tool" registry pattern: each sub-agent runs in its
    own isolated context (its own ReAct loop + tools) and only its final answer
    is returned to the parent, keeping the parent's context window clean.
    """
    if not specs:
        raise ValueError("build_subagent_dispatcher requires at least one SubAgentSpec")

    from langchain_core.tools import StructuredTool

    from ..swarm.subagent import make_subagent_tool

    names = tuple(s.name for s in specs)
    by_name = {
        s.name: make_subagent_tool(
            name=s.name,
            description=s.description,
            system_prompt=s.prompt,
            tools=s.tools,
            provider=s.provider,
            model=s.model,
            recursion_limit=recursion_limit,
        )
        for s in specs
    }
    catalog = "\n".join(f"- {s.name}: {s.description}" for s in specs)

    class TaskInput(BaseModel):
        subagent_type: Literal[names] = Field(description="Which sub-agent to delegate to.")
        task: str = Field(description="The task, question, or instruction to delegate.")

    def _dispatch(subagent_type: str) -> Any:
        sub = by_name.get(subagent_type)
        if sub is None:
            raise ValueError(f"Unknown subagent_type {subagent_type!r}. Available: {list(names)}")
        return sub

    def _run(subagent_type: str, task: str) -> str:
        try:
            return _dispatch(subagent_type).invoke({"task": task})
        except ValueError as exc:
            return str(exc)

    async def _arun(subagent_type: str, task: str) -> str:
        try:
            return await _dispatch(subagent_type).ainvoke({"task": task})
        except ValueError as exc:
            return str(exc)

    return StructuredTool.from_function(
        func=_run,
        coroutine=_arun,
        name="task",
        description=f"Delegate a focused subtask to a specialist sub-agent. Available sub-agents:\n{catalog}",
        args_schema=TaskInput,
    )


# ──────────────────────────────────────────────────────────────────────────────
# 4. Reflection
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class ReflectionConfig:
    """Configuration for the critic/reflection revision loop."""

    enabled: bool = False
    max_revisions: int = 2
    critic_prompt: str = field(default=(
        "You are a strict reviewer. Given the ORIGINAL TASK and the DRAFT ANSWER, "
        "respond with exactly 'APPROVE' if the draft fully satisfies the task, or "
        "'REVISE: <specific, actionable feedback>' if it does not."
    ))


def _last_text(messages: Sequence[Any]) -> str:
    for m in reversed(messages):
        content = getattr(m, "content", "")
        if content and isinstance(content, str):
            return content
    return ""


async def run_with_reflection(
    agent: Any,
    messages: list,
    *,
    provider: str,
    model: str | None,
    reflection: ReflectionConfig,
    recursion_limit: int = 40,
    thread_id: str = "auto",
) -> tuple[list, int]:
    """Run ``agent.ainvoke`` once, then — if reflection is enabled — critique the
    draft and feed revision requests back into the same agent (same thread, so
    it keeps its tool-call history) up to ``max_revisions`` times.

    Returns ``(final_messages, revisions_used)``.
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    from ..providers import get_chat_model

    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": recursion_limit}
    result = await agent.ainvoke({"messages": messages}, config=config)
    msgs = result.get("messages", [])
    if not reflection.enabled:
        return msgs, 0

    critic = get_chat_model(provider, model)
    original_task = _last_text(messages)
    revisions = 0
    while revisions < reflection.max_revisions:
        draft = _last_text(msgs)
        verdict = await critic.ainvoke([
            SystemMessage(reflection.critic_prompt),
            HumanMessage(f"ORIGINAL TASK:\n{original_task}\n\nDRAFT ANSWER:\n{draft}"),
        ])
        verdict_text = str(verdict.content or "").strip()
        if verdict_text.upper().startswith("APPROVE"):
            break
        feedback = verdict_text.split(":", 1)[1].strip() if ":" in verdict_text else verdict_text
        revisions += 1
        result = await agent.ainvoke(
            {"messages": [HumanMessage(
                f"A reviewer asked for changes: {feedback}\n"
                "Please revise your previous answer accordingly."
            )]},
            config=config,
        )
        msgs = result.get("messages", [])
    return msgs, revisions


# ──────────────────────────────────────────────────────────────────────────────
# 5. Compaction
# ──────────────────────────────────────────────────────────────────────────────

def compact_messages(messages: list, llm: Any, *, keep_last: int = 6, token_limit: int = 6000) -> list:
    """Summarise older messages into one ``SystemMessage`` once the transcript
    exceeds ``token_limit`` (rough token estimate), keeping the most recent
    ``keep_last`` messages verbatim. No-op if the transcript is already short.
    Synchronous — makes one blocking LLM call.
    """
    from langchain_core.messages import SystemMessage

    from ..insights import count_tokens

    if len(messages) <= keep_last:
        return messages
    blob = "\n".join(str(getattr(m, "content", "")) for m in messages)
    if count_tokens(blob) <= token_limit:
        return messages

    older, recent = messages[:-keep_last], messages[-keep_last:]
    older_text = "\n".join(f"{getattr(m, 'type', 'message')}: {getattr(m, 'content', '')}" for m in older)
    summary = llm.invoke([
        SystemMessage("Summarise the following conversation history concisely, preserving key facts, decisions, and open tasks."),
        {"role": "user", "content": older_text[:20000]},
    ])
    return [SystemMessage(f"[Earlier conversation summary]\n{summary.content}")] + list(recent)


# ──────────────────────────────────────────────────────────────────────────────
# Standalone convenience: DeepAgent
# ──────────────────────────────────────────────────────────────────────────────

class DeepAgentConfig(BaseModel):
    """Configuration for a standalone :class:`DeepAgent` run."""

    goal: str = Field(..., min_length=1, max_length=8000)
    provider: str = "openai"
    model: str = ""
    workspace: str = "./workspace"
    extra_tools: list[Any] = Field(default_factory=list)
    subagents: list[SubAgentSpec] = Field(default_factory=list)
    use_planning: bool = True
    use_filesystem: bool = True
    reflection: ReflectionConfig = Field(default_factory=ReflectionConfig)
    max_iterations: int = Field(default=25, ge=1)
    compaction_token_limit: int = Field(default=6000, ge=500)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    guard_input: bool = True

    model_config = {"extra": "allow", "arbitrary_types_allowed": True}


@dataclass
class DeepAgentResult:
    goal: str
    summary: str
    iterations: int
    revisions: int
    todos: list[Todo]
    artifacts: list[Path]
    subagents_used: list[str]
    success: bool
    error: str | None = None

    def __str__(self) -> str:
        status = "✓" if self.success else "✗"
        parts = [
            f"{status} Goal: {self.goal}",
            f"  Iterations: {self.iterations}  Revisions: {self.revisions}",
            f"  Todos: {[t.content for t in self.todos]}",
            f"  Sub-agents used: {self.subagents_used}",
        ]
        if not self.success and self.error:
            parts.append(f"  Error: {self.error}")
        parts.append(f"  Summary: {self.summary[:300]}")
        return "\n".join(parts)


_DEEP_SYSTEM_TEMPLATE = textwrap.dedent("""\
    You are a deep agent: a goal-directed AI with planning, filesystem, and
    delegation tools. Your goal is:

    {goal}

    You have a workspace at: {workspace}

    Work methodically:
    1. If a write_todos tool is available, record your plan before acting and
       update it as you complete each step.
    2. Use your tools to gather information, delegate focused subtasks to
       sub-agents when available (via the 'task' tool), and write artifacts to
       the workspace.
    3. When done, provide a clear final answer starting with "FINAL ANSWER:".

    The user cannot give you additional input — work autonomously.
""")


class DeepAgent:
    """A goal-directed agent with planning, filesystem, sub-agent delegation,
    and an optional reflection loop. Use :meth:`create` as the entry point.
    """

    def __init__(self, config: DeepAgentConfig) -> None:
        self.config = config
        self.workspace = Path(config.workspace).expanduser().resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)

    @classmethod
    def create(
        cls,
        goal: str,
        provider: str = "openai",
        model: str = "",
        workspace: str = "./workspace",
        **kwargs: Any,
    ) -> "DeepAgent":
        """Create a DeepAgent from keyword arguments."""
        return cls(DeepAgentConfig(goal=goal, provider=provider, model=model, workspace=workspace, **kwargs))

    def run(self) -> DeepAgentResult:
        """Run the agent synchronously (see :func:`agentx.agents.autonomous._run_sync`)."""
        from .autonomous import _run_sync

        return _run_sync(self.arun())

    async def arun(self) -> DeepAgentResult:
        """Async run — use this from an async context."""
        from langchain_core.messages import HumanMessage
        from langgraph.checkpoint.memory import MemorySaver
        from langgraph.prebuilt import create_react_agent

        from ..providers import get_chat_model
        from ..tools import tool_call_coercion_hook

        cfg = self.config
        goal = cfg.goal
        if cfg.guard_input:
            from ..guardrails import apply_guards, default_input_guards

            guarded = apply_guards(goal, default_input_guards(max_chars=8000))
            goal = guarded.text
            if guarded.violations:
                logger.info("Input guards applied: %s", guarded.violations)

        llm = get_chat_model(cfg.provider, cfg.model or None, temperature=cfg.temperature)

        tools = list(cfg.extra_tools)
        todos_box: dict[str, list[Todo]] = {"todos": []}
        if cfg.use_planning:
            planning_tool, todos_box = make_planning_tool()
            tools.append(planning_tool)
        if cfg.use_filesystem:
            tools.extend(make_filesystem_tools(self.workspace))
        if cfg.subagents:
            tools.append(build_subagent_dispatcher(cfg.subagents))

        system = _DEEP_SYSTEM_TEMPLATE.format(goal=goal, workspace=str(self.workspace))

        try:
            agent = create_react_agent(
                llm, tools, prompt=system,
                post_model_hook=tool_call_coercion_hook(tools),
                checkpointer=MemorySaver(),
            )

            logger.info(
                "DeepAgent starting: goal=%r subagents=%s reflection=%s",
                cfg.goal[:80], [s.name for s in cfg.subagents], cfg.reflection.enabled,
            )

            messages, revisions = await run_with_reflection(
                agent, [HumanMessage(content=goal)],
                provider=cfg.provider, model=cfg.model or None,
                reflection=cfg.reflection, recursion_limit=cfg.max_iterations * 2,
            )

            final_content = _last_text(messages)
            summary = final_content
            if "FINAL ANSWER:" in final_content:
                summary = final_content.split("FINAL ANSWER:", 1)[1].strip()

            artifacts = [f for f in self.workspace.rglob("*") if f.is_file()]
            logger.info("DeepAgent finished. Artifacts: %d, revisions: %d", len(artifacts), revisions)
            return DeepAgentResult(
                goal=cfg.goal,
                summary=summary,
                iterations=len([m for m in messages if getattr(m, "type", "") == "tool"]),
                revisions=revisions,
                todos=list(todos_box.get("todos", [])),
                artifacts=artifacts,
                subagents_used=[s.name for s in cfg.subagents],
                success=True,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("DeepAgent failed")
            return DeepAgentResult(
                goal=cfg.goal, summary="", iterations=0, revisions=0, todos=[],
                artifacts=[], subagents_used=[], success=False, error=str(exc),
            )
