"""CrewAI adapter — build Agents and a Crew from common inputs.

Uses our provider factory's ``get_crewai_llm`` so the same provider ids work
across frameworks. Requires ``agentx-kit[crewai]``.
"""
from __future__ import annotations

from typing import Any

from ..providers import get_crewai_llm


def _require_crewai():
    try:
        import crewai  # type: ignore

        return crewai
    except ImportError as exc:
        raise ImportError(
            "CrewAI is required. Install with: uv pip install 'agentx-kit[crewai]'"
        ) from exc


def build_crewai_agent(
    role: str,
    goal: str,
    backstory: str = "",
    provider: str | None = None,
    model: str | None = None,
    tools: list[Any] | None = None,
    **kwargs: Any,
):
    """Return a configured CrewAI ``Agent``."""
    crewai = _require_crewai()
    llm = get_crewai_llm(provider, model)
    return crewai.Agent(
        role=role,
        goal=goal,
        backstory=backstory or f"An expert acting as {role}.",
        tools=tools or [],
        llm=llm,
        verbose=kwargs.pop("verbose", True),
        allow_delegation=kwargs.pop("allow_delegation", False),
        **kwargs,
    )


def build_crew(agents: list[Any], tasks: list[Any], **kwargs: Any):
    """Return a CrewAI ``Crew`` from agents + tasks (sequential by default)."""
    crewai = _require_crewai()
    process = kwargs.pop("process", None) or crewai.Process.sequential
    return crewai.Crew(agents=agents, tasks=tasks, process=process, verbose=kwargs.pop("verbose", True), **kwargs)
