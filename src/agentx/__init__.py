"""AgentX — provider-agnostic agentic framework + project scaffolder.

Quick start (library):

    from agentx import get_chat_model
    llm = get_chat_model("openai", "gpt-4o-mini")
    print(llm.invoke("Hello").content)

Quick start (scaffolder):

    $ agentx new            # interactive wizard → generates a uv project

Public API is intentionally small and stable; capability modules (rag, memory,
tools, skills, frameworks) are imported lazily so installing one provider extra
is enough to get started.
"""
from __future__ import annotations

__version__ = "0.17.1"

from .providers import (  # noqa: E402
    ProviderSpec,
    get_chat_model,
    get_crewai_llm,
    list_providers,
)
from .guardrails import GuardrailError, apply_guards  # noqa: E402
from .agents import AgentResult, AutonomousAgent, ResearchAgent, ResearchResult  # noqa: E402
from .logging_config import get_logger, setup_logging  # noqa: E402
from .observability import get_callbacks, setup_tracing, telemetry_enabled  # noqa: E402
from .rag import (  # noqa: E402
    AnyEmbeddingConfig,
    AzureOpenAIEmbeddingConfig,
    BedrockEmbeddingConfig,
    CohereEmbeddingConfig,
    EmbeddingConfig,
    GoogleEmbeddingConfig,
    HuggingFaceEmbeddingConfig,
    OllamaEmbeddingConfig,
    OpenAIEmbeddingConfig,
    VoyageEmbeddingConfig,
    auto_embeddings,
    get_embeddings,
)
from .reliability import (  # noqa: E402
    RateLimiter,
    UsageLimitExceeded,
    UsageLimits,
    UsageTracker,
    build_resilient_chat,
    rate_limited_callback,
)
from .structured import structured_model  # noqa: E402
from .insights import (  # noqa: E402
    analyze_prompt,
    count_tokens,
    estimate_cost,
    optimize_prompt,
)
from .cache import cache_stats, clear_cache, disable_caching, enable_caching  # noqa: E402

__all__ = [
    "__version__",
    # providers
    "ProviderSpec",
    "get_chat_model",
    "get_crewai_llm",
    "list_providers",
    # logging
    "setup_logging",
    "get_logger",
    # agents
    "AutonomousAgent",
    "ResearchAgent",
    "AgentResult",
    "ResearchResult",
    # embeddings
    "get_embeddings",
    "auto_embeddings",
    "EmbeddingConfig",
    "AnyEmbeddingConfig",
    "HuggingFaceEmbeddingConfig",
    "OpenAIEmbeddingConfig",
    "AzureOpenAIEmbeddingConfig",
    "CohereEmbeddingConfig",
    "GoogleEmbeddingConfig",
    "BedrockEmbeddingConfig",
    "VoyageEmbeddingConfig",
    "OllamaEmbeddingConfig",
    # enterprise runtime
    "setup_tracing",
    "get_callbacks",
    "telemetry_enabled",
    "build_resilient_chat",
    "UsageLimits",
    "UsageTracker",
    "UsageLimitExceeded",
    "RateLimiter",
    "rate_limited_callback",
    "apply_guards",
    "GuardrailError",
    "structured_model",
    # prompt insights
    "analyze_prompt",
    "optimize_prompt",
    "count_tokens",
    "estimate_cost",
    # response caching
    "enable_caching",
    "disable_caching",
    "cache_stats",
    "clear_cache",
]
