"""Autonomous and research agents for agentx.

    from agentx.agents import AutonomousAgent, ResearchAgent

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
"""
from .autonomous import AgentResult, AutonomousAgent, AutonomousAgentConfig
from .research import ResearchAgent, ResearchAgentConfig, ResearchResult

__all__ = [
    "AutonomousAgent",
    "AutonomousAgentConfig",
    "AgentResult",
    "ResearchAgent",
    "ResearchAgentConfig",
    "ResearchResult",
]
