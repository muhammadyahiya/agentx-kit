"""Research agent — a multi-step agent that plans a research task, searches the
web, visits source URLs, synthesises findings, and produces a structured report.

Designed for tasks like:
  - "Compare top-5 open-source LLM frameworks in 2025"
  - "Summarise recent papers on RAG hallucination"
  - "Research cloud GPU pricing across AWS, GCP, and Azure"

Usage::

    from agentx.agents import ResearchAgent

    agent = ResearchAgent.create(
        topic="Transformer model architectures in 2025",
        provider="anthropic",
        depth="deep",       # 'quick' | 'standard' | 'deep'
        output_file="report.md",
    )
    report = agent.run()
    print(report.markdown)
"""
from __future__ import annotations

import logging
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from .autonomous import _run_sync

logger = logging.getLogger(__name__)

ResearchDepth = Literal["quick", "standard", "deep"]

_DEPTH_PARAMS: dict[ResearchDepth, dict] = {
    "quick":    {"max_queries": 3,  "max_urls": 2,  "max_iterations": 15},
    "standard": {"max_queries": 6,  "max_urls": 5,  "max_iterations": 25},
    "deep":     {"max_queries": 12, "max_urls": 10, "max_iterations": 40},
}


# ──────────────────────────────────────────────────────────────────────────────
# Pydantic config
# ──────────────────────────────────────────────────────────────────────────────

class ResearchAgentConfig(BaseModel):
    """Configuration for a ResearchAgent."""

    topic: str = Field(..., min_length=1, description="Research question or topic.")
    provider: str = "openai"
    model: str = ""
    depth: ResearchDepth = "standard"
    output_file: str | None = Field(
        default=None,
        description="Write the final report to this path. None = return only.",
    )
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    include_citations: bool = True
    report_format: Literal["markdown", "plain"] = "markdown"

    model_config = {"extra": "allow"}

    @field_validator("topic")
    @classmethod
    def _strip_topic(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("topic must not be empty or whitespace-only")
        return stripped


# ──────────────────────────────────────────────────────────────────────────────
# Result
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class ResearchResult:
    topic: str
    markdown: str
    citations: list[str]
    queries_run: int
    urls_visited: int
    success: bool
    error: str | None = None

    def __str__(self) -> str:
        return self.markdown

    def save(self, path: str | Path) -> None:
        """Write the report to ``path`` (creating parent dirs as needed)."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.markdown, encoding="utf-8")
        logger.info("Research report saved to %s", p)


# ──────────────────────────────────────────────────────────────────────────────
# System prompt
# ──────────────────────────────────────────────────────────────────────────────

_RESEARCH_SYSTEM = textwrap.dedent("""\
    You are a meticulous research agent. Your job is to thoroughly research the topic:

    TOPIC: {topic}

    Research protocol:
    1. PLAN: Decompose the topic into 3-6 specific sub-questions.
    2. SEARCH: Run targeted web searches for each sub-question.
    3. READ: Fetch and read the most promising URLs for primary sources.
    4. SYNTHESISE: Combine findings, cross-check facts, note disagreements.
    5. REPORT: Write a comprehensive, well-structured {format} report.

    Guidelines:
    - Always cite your sources with URLs in [1], [2] notation.
    - Prefer primary sources (papers, official docs, GitHub) over blogs.
    - Acknowledge uncertainty where sources conflict.
    - The report must be self-contained — the reader has not seen the raw search results.
    - End with a "## References" section listing all URLs used.

    Use 'think' to plan before searching. Use 'web_search' to find information.
    Use 'fetch_url' to read important pages in detail.
    When you have sufficient information, write the final report.
    Start the final report with "## RESEARCH REPORT:" on its own line.
""")


def _make_research_tools(cfg: ResearchAgentConfig) -> tuple[list, list[str]]:
    """Build research-specific tools and return them alongside the citations list.

    Returns:
        ``(tools, citations)`` — ``citations`` is the same list the fetch_url
        tool appends to, so callers can read it after the agent finishes.
    """
    from langchain_core.tools import tool
    from ..tools.builtin import fetch_url as _fetch_url

    params = _DEPTH_PARAMS[cfg.depth]
    _query_count = [0]
    _url_count = [0]
    _citations: list[str] = []

    @tool
    def web_search(query: str) -> str:
        """Search the web. Use precise, specific queries for best results."""
        if _query_count[0] >= params["max_queries"]:
            return "Search limit reached. Synthesise from gathered information."
        from ..tools.builtin import web_search as _search
        _query_count[0] += 1
        logger.info("Research search #%d: %r", _query_count[0], query[:80])
        return _search(query, max_results=5)

    @tool
    def fetch_url(url: str) -> str:
        """Fetch and return the text content of a URL. Use for primary sources."""
        if _url_count[0] >= params["max_urls"]:
            return "URL fetch limit reached. Synthesise from gathered information."
        _url_count[0] += 1
        if url not in _citations:
            _citations.append(url)
        logger.info("Research fetch #%d: %s", _url_count[0], url)
        return _fetch_url(url, max_chars=10000)

    @tool
    def think(reasoning: str) -> str:
        """Think step-by-step before deciding what to search or how to structure the report."""
        logger.debug("Research thinking: %s", reasoning[:200])
        return "Thinking noted."

    return [web_search, fetch_url, think], _citations


# ──────────────────────────────────────────────────────────────────────────────
# ResearchAgent
# ──────────────────────────────────────────────────────────────────────────────

class ResearchAgent:
    """Multi-step research agent with web search, URL fetching, and report writing."""

    def __init__(self, config: ResearchAgentConfig) -> None:
        self.config = config

    @classmethod
    def create(
        cls,
        topic: str,
        provider: str = "openai",
        model: str = "",
        depth: ResearchDepth = "standard",
        output_file: str | None = None,
        **kwargs: Any,
    ) -> "ResearchAgent":
        return cls(ResearchAgentConfig(
            topic=topic, provider=provider, model=model,
            depth=depth, output_file=output_file, **kwargs,
        ))

    def run(self) -> ResearchResult:
        """Run the research agent synchronously.

        Safe to call from FastAPI/Jupyter/Streamlit — see ``_run_sync`` in
        ``autonomous.py``.
        """
        return _run_sync(self.arun())

    async def arun(self) -> ResearchResult:
        """Async run — use from an async context."""
        from ..providers import get_chat_model

        cfg = self.config
        params = _DEPTH_PARAMS[cfg.depth]
        llm = get_chat_model(cfg.provider, cfg.model or None, temperature=cfg.temperature)
        tools, citations = _make_research_tools(cfg)

        system = _RESEARCH_SYSTEM.format(
            topic=cfg.topic,
            format=cfg.report_format,
        )

        try:
            from langgraph.prebuilt import create_react_agent  # type: ignore
            from langgraph.checkpoint.memory import MemorySaver  # type: ignore
            from langchain_core.messages import HumanMessage  # type: ignore

            agent = create_react_agent(llm, tools, prompt=system, checkpointer=MemorySaver())

            logger.info(
                "ResearchAgent starting: topic=%r depth=%s", cfg.topic[:60], cfg.depth
            )

            result = await agent.ainvoke(
                {"messages": [HumanMessage(content=f"Research this topic thoroughly: {cfg.topic}")]},
                config={
                    "configurable": {"thread_id": "research"},
                    "recursion_limit": params["max_iterations"] * 2,
                },
            )

            messages = result.get("messages", [])
            final_content = ""
            for m in reversed(messages):
                c = getattr(m, "content", "")
                if c and isinstance(c, str) and len(c) > 100:
                    final_content = c
                    break

            # Extract the report section
            report_md = final_content
            if "## RESEARCH REPORT:" in final_content:
                report_md = final_content.split("## RESEARCH REPORT:", 1)[1].strip()

            # Append citations if not already in the report
            if cfg.include_citations and citations and "## References" not in report_md:
                refs = "\n".join(f"{i+1}. {url}" for i, url in enumerate(citations))
                report_md += f"\n\n## References\n{refs}"

            tool_calls = sum(1 for m in messages if getattr(m, "type", "") == "tool")
            queries_run = sum(
                1 for m in messages
                if getattr(m, "type", "") == "tool" and getattr(m, "name", "") == "web_search"
            )
            urls_visited = sum(
                1 for m in messages
                if getattr(m, "type", "") == "tool" and getattr(m, "name", "") == "fetch_url"
            )

            research_result = ResearchResult(
                topic=cfg.topic,
                markdown=report_md,
                citations=citations,
                queries_run=queries_run,
                urls_visited=urls_visited,
                success=True,
            )

            if cfg.output_file:
                research_result.save(cfg.output_file)

            logger.info(
                "ResearchAgent done: queries=%d urls=%d citations=%d",
                queries_run, urls_visited, len(citations),
            )
            return research_result

        except Exception as exc:  # noqa: BLE001
            logger.exception("ResearchAgent failed")
            return ResearchResult(
                topic=cfg.topic,
                markdown="",
                citations=[],
                queries_run=0,
                urls_visited=0,
                success=False,
                error=str(exc),
            )
