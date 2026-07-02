"""``ProjectSpec`` — the single source of truth for a generation run.

Both the interactive wizard and the programmatic API produce a ``ProjectSpec``;
the generator consumes it. Keeping this validated and standalone makes the whole
scaffolder testable without a TTY.
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Framework = Literal["langgraph", "crewai"]
MemoryMode = Literal["none", "short", "long", "both"]
PromptStyle = Literal["default", "custom"]
VectorStoreBackend = Literal["chroma", "faiss", "memory"]
AgentMode = Literal["chat", "autonomous", "research"]

# How multiple agents are wired together (LangGraph only; CrewAI always uses sequential crew).
#   supervisor  — an LLM router decides which worker acts next (dynamic, context-aware)
#   sequential  — agents run in order: agent_1 → agent_2 → … (pipeline / chain-of-thought)
#   parallel    — all agents handle the same input simultaneously; results are merged
OrchestrationMode = Literal["supervisor", "sequential", "parallel"]


def to_snake(name: str) -> str:
    s = re.sub(r"[^0-9a-zA-Z]+", "_", name.strip().lower()).strip("_")
    return s or "app"


class AgentSpec(BaseModel):
    name: str = "assistant"
    role: str = "Helpful Assistant"
    goal: str = "Help the user accomplish their task accurately."
    # Optional explicit system prompt. Blank → derived from role/goal at runtime.
    system_prompt: str = ""

    @field_validator("name")
    @classmethod
    def _slug(cls, v: str) -> str:
        return to_snake(v)


_KNOWN_EMBEDDING_PROVIDERS = frozenset({
    "", "huggingface", "hf", "openai", "azure", "cohere",
    "google", "bedrock", "aws", "voyage", "ollama",
})


class ProjectSpec(BaseModel):
    name: str = Field(..., min_length=1, description="Project name (directory + package base).")
    framework: Framework = "langgraph"
    provider: str = "openai"
    model: str = ""                       # blank → provider default
    agents: list[AgentSpec] = Field(default_factory=lambda: [AgentSpec()])
    # How agents are connected (only meaningful when len(agents) > 1 and framework == langgraph).
    orchestration: OrchestrationMode = "supervisor"
    use_rag: bool = False
    vector_store: VectorStoreBackend = "chroma"
    embedding_provider: str = ""     # blank → auto-detect (HF local → OpenAI → Ollama)
    agent_mode: AgentMode = "chat"   # chat | autonomous | research
    # Domain seeding: "" = auto-infer from name/problem_statement; "none" = force
    # generic; else an explicit domain key (legal, medical, finance, …).
    domain: str = ""
    seed_domain_kb: bool = True
    problem_statement: str = ""      # optional free text used for domain inference
    memory: MemoryMode = "none"
    use_mcp: bool = False
    use_skills: bool = False
    # ----- voice / swarm / channels / UI -----
    use_voice: bool = False        # speech-to-text + text-to-speech I/O helpers
    use_subagents: bool = False    # attach sub-agents (agent-as-tool) to each agent
    streamlit: bool = False        # generate a Streamlit UI (chat + optional voice)
    claw: bool = False             # multi-channel content assistant (webhook + intent router)
    prompt_style: PromptStyle = "default"
    # ----- enterprise features -----
    observability: bool = False   # OpenTelemetry / Langfuse tracing wiring
    guardrails: bool = False      # input/output guardrails module
    serve: bool = False           # FastAPI server (REST + SSE streaming)
    docker: bool = False          # Dockerfile + docker-compose.yml
    ci: bool = False              # GitHub Actions (lint + test [+ eval])
    evals: bool = False           # LLM-as-judge eval harness (+ CI gate)
    use_cache: bool = False       # global LLM response cache (cost/latency saver)
    create_venv: bool = True
    run_sync: bool = False
    # When set, generated pyproject depends on agentx from this local path
    # (editable) instead of PyPI — used for local dev/testing.
    agentx_local_path: str | None = None

    def enable_enterprise(self) -> "ProjectSpec":
        """Turn on the full enterprise feature set in one call."""
        self.observability = self.guardrails = self.serve = True
        self.docker = self.ci = self.evals = self.use_cache = True
        return self

    @property
    def package(self) -> str:
        return to_snake(self.name)

    @property
    def slug(self) -> str:
        return re.sub(r"[^0-9a-zA-Z]+", "-", self.name.strip().lower()).strip("-") or "app"

    @property
    def needs_memory(self) -> bool:
        return self.memory != "none"

    @property
    def use_short_memory(self) -> bool:
        return self.memory in ("short", "both")

    @property
    def use_long_memory(self) -> bool:
        return self.memory in ("long", "both")

    @property
    def multi_agent(self) -> bool:
        return len(self.agents) > 1

    @field_validator("embedding_provider")
    @classmethod
    def _validate_embedding_provider(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if v not in _KNOWN_EMBEDDING_PROVIDERS:
            raise ValueError(
                f"embedding_provider must be one of {sorted(_KNOWN_EMBEDDING_PROVIDERS - {''})} "
                f"or '' for auto-detect (got {v!r})"
            )
        return v

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be empty or whitespace-only")
        return v
