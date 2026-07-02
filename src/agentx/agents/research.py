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
import re
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from .autonomous import _run_sync

logger = logging.getLogger(__name__)

ResearchDepth = Literal["quick", "standard", "deep"]

_URL_RE = re.compile(r"https?://[^\s\)\]\}>\"']+")


def _extract_urls(text: str) -> list[str]:
    """Return unique URLs found in ``text``, in order of first appearance."""
    seen: list[str] = []
    for url in _URL_RE.findall(text or ""):
        url = url.rstrip(".,;")
        if url not in seen:
            seen.append(url)
    return seen


def _parse_lines(text: str) -> list[str]:
    """Parse an LLM list reply (newline- or JSON-array-formatted) into strings."""
    text = (text or "").strip()
    # Try a JSON array first.
    if text.startswith("["):
        import json as _json

        try:
            data = _json.loads(text)
            if isinstance(data, list):
                return [str(x).strip() for x in data if str(x).strip()]
        except (ValueError, TypeError):
            pass
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip().lstrip("-*0123456789.)( ").strip()
        if line:
            lines.append(line)
    return lines

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

    topic: str = Field(..., min_length=1, max_length=4000, description="Research question or topic.")
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
    guard_input: bool = Field(
        default=True,
        description="Apply default_input_guards to the research topic before running.",
    )

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
        """Async run — use from an async context.

        Uses a deterministic **plan → search → (fetch) → synthesise** pipeline
        rather than relying on the model to emit perfect tool calls. This is
        robust across providers, including small/local models (llama3.2) that
        otherwise hallucinate tool names and never actually search.
        """
        from ..providers import get_chat_model

        cfg = self.config
        params = _DEPTH_PARAMS[cfg.depth]

        topic = cfg.topic
        if cfg.guard_input:
            from ..guardrails import apply_guards, default_input_guards
            result = apply_guards(topic, default_input_guards(max_chars=4000))
            topic = result.text
            if result.violations:
                logger.info("Input guards applied to topic: %s", result.violations)

        try:
            llm = get_chat_model(cfg.provider, cfg.model or None, temperature=cfg.temperature)
            logger.info("ResearchAgent starting: topic=%r depth=%s", topic[:60], cfg.depth)

            # 1. PLAN — decompose the topic into targeted sub-questions.
            subquestions = await self._plan(llm, topic, params["max_queries"])

            # 2. SEARCH — run each sub-question through web search (direct calls).
            from ..tools.builtin import web_search

            findings: list[tuple[str, str]] = []
            citations: list[str] = []
            for question in subquestions[: params["max_queries"]]:
                snippet = web_search(question, max_results=4)
                findings.append((question, snippet))
                for url in _extract_urls(snippet):
                    if url not in citations:
                        citations.append(url)
            queries_run = len(findings)

            # 3. FETCH — read the most promising sources for deeper detail.
            urls_visited = 0
            if params["max_urls"] and citations:
                from ..tools.builtin import fetch_url

                for url in citations[: params["max_urls"]]:
                    page = fetch_url(url, max_chars=6000)
                    findings.append((f"[source] {url}", page))
                    urls_visited += 1

            # 4. SYNTHESISE — write the report grounded in the gathered material.
            report_md = await self._synthesise(llm, topic, findings, citations)

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

    async def _plan(self, llm, topic: str, max_q: int) -> list[str]:
        """Decompose ``topic`` into up to ``max_q`` specific sub-questions.

        Parses newline- or JSON-formatted output leniently; always returns at
        least the original topic so the pipeline can proceed.
        """
        from langchain_core.messages import HumanMessage, SystemMessage

        prompt = (
            f"Break the research topic into {max_q} specific, non-overlapping "
            "sub-questions that together cover it well. Reply with ONE "
            "sub-question per line, no numbering, no preamble."
        )
        try:
            resp = await llm.ainvoke([SystemMessage(prompt), HumanMessage(f"TOPIC: {topic}")])
            questions = _parse_lines(str(resp.content or ""))
        except Exception:  # noqa: BLE001
            logger.warning("planning step failed; searching the topic directly", exc_info=True)
            questions = []
        questions = [q for q in questions if len(q) > 3][:max_q]
        return questions or [topic]

    async def _synthesise(self, llm, topic: str, findings: list[tuple[str, str]], citations: list[str]) -> str:
        """Write the final report from the gathered findings, with references."""
        from langchain_core.messages import HumanMessage, SystemMessage

        context = "\n\n".join(f"### {q}\n{text}" for q, text in findings)[:12000]
        system = _RESEARCH_SYSTEM.format(topic=topic, format=self.config.report_format)
        instruction = (
            "Using ONLY the research material below, write a comprehensive, "
            f"well-structured {self.config.report_format} report answering the topic. "
            "Cite sources inline as [1], [2] matching the reference order. Do NOT "
            "invent facts or sources.\n\nRESEARCH MATERIAL:\n" + context
        )
        resp = await llm.ainvoke([SystemMessage(system), HumanMessage(instruction)])
        report = str(resp.content or "").strip()
        if "## RESEARCH REPORT:" in report:
            report = report.split("## RESEARCH REPORT:", 1)[1].strip()
        if self.config.include_citations and citations and "## References" not in report:
            refs = "\n".join(f"{i + 1}. {url}" for i, url in enumerate(citations))
            report += f"\n\n## References\n{refs}"
        return report
