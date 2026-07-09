"""Autonomous, research, and deep agents for agentx.

    from agentx.agents import AutonomousAgent, ResearchAgent, DeepAgent

    # Autonomous agent — goal-directed, uses tools autonomously
    agent = AutonomousAgent.create(
        goal="Research top RAG frameworks and write a comparison report.",
        provider="openai",
        workspace="./workspace",
    )
    result = agent.run()
    print(result.summary)

    # Research agent — structured multi-step research with citations
    research = ResearchAgent.create(
        topic="LLM inference optimisation in 2025",
        depth="deep",
        output_file="report.md",
    )
    report = research.run()
    print(report.markdown)

    # Deep agent — planning (todo-list), filesystem, sub-agent delegation, and
    # an optional critic/reflection revision loop.
    deep = DeepAgent.create(
        goal="Audit this repo's error handling and write a report.",
        provider="openai",
        workspace="./workspace",
    )
    result = deep.run()
    print(result.summary)
"""
from .autonomous import AgentResult, AutonomousAgent, AutonomousAgentConfig
from .deep_agent import (
    DeepAgent,
    DeepAgentConfig,
    DeepAgentResult,
    ReflectionConfig,
    SubAgentSpec,
    Todo,
    build_subagent_dispatcher,
    compact_messages,
    make_filesystem_tools,
    make_planning_tool,
    run_with_reflection,
)
from .research import ResearchAgent, ResearchAgentConfig, ResearchResult

__all__ = [
    "AutonomousAgent",
    "AutonomousAgentConfig",
    "AgentResult",
    "ResearchAgent",
    "ResearchAgentConfig",
    "ResearchResult",
    "DeepAgent",
    "DeepAgentConfig",
    "DeepAgentResult",
    "Todo",
    "SubAgentSpec",
    "ReflectionConfig",
    "make_planning_tool",
    "make_filesystem_tools",
    "build_subagent_dispatcher",
    "run_with_reflection",
    "compact_messages",
]
