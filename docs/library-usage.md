# Package usage (Python API)

AgentX-Kit's building blocks work standalone — you don't need to scaffold a project to use them.
The public API (`import agentx`) is intentionally small and stable; capability modules (RAG,
memory, tools, skills, frameworks) are imported lazily so installing one provider extra is enough
to get started.

```bash
pip install "agentx-kit[openai]"   # or any provider extra you need
```

```python
import agentx
print(agentx.__version__)   # "1.1.0"
```

## Why

- **One factory, every provider.** `get_chat_model("bedrock", ...)` or
  `get_chat_model("openrouter", ...)` — same call, lazy imports, install only the extras you use.
- **Two frameworks.** LangChain/LangGraph *and* CrewAI from the same building blocks.
- **Batteries included.** RAG, short/long-term memory, MCP tools, and a skills registry — each
  optional and gracefully degrading.
- **Scaffolder, not a black box.** The generated project is readable, idiomatic code you own,
  pre-wired to your selections, in a fresh `.venv`.

---

## 1. Chat models — `agentx.get_chat_model` / `get_crewai_llm`

```python
from agentx import get_chat_model, list_providers, ProviderSpec

llm = get_chat_model("openai", "gpt-4o-mini")
print(llm.invoke("Say hi in 3 words").content)

for spec in list_providers():
    print(spec.id, "→", spec.label, spec.env_vars)
```

`get_chat_model(provider, model=None, **kwargs)` returns a LangChain `BaseChatModel` — pass any
`ChatOpenAI`/`ChatAnthropic`/etc. kwarg through (`temperature`, `max_tokens`, …). See
[Providers](providers.md) for the full id → env-var table.

CrewAI:

```python
from agentx import get_crewai_llm
llm = get_crewai_llm("openrouter", "anthropic/claude-3.5-sonnet")
```

---

## 2. Autonomous & research agents — `agentx.AutonomousAgent` / `ResearchAgent`

```python
from agentx import AutonomousAgent, AgentResult

result: AgentResult = AutonomousAgent.create(
    goal="Research the top 5 RAG frameworks and write a report",
    provider="openai",
    workspace="./workspace",
    max_iter=20,
).run()
print(result.summary, result.iterations)
```

```python
from agentx import ResearchAgent, ResearchResult

result: ResearchResult = ResearchAgent.create(
    topic="LLM inference optimisation 2025",
    provider="openai",
    depth="deep",       # quick | standard | deep
).run()
print(result.report)     # markdown, with citations
print(result.sources)
```

These back [`agentx agent run`](cli/agent.md#agentx-agent-run) and
[`agentx agent research`](cli/agent.md#agentx-agent-research).

## 3. Deep agents — `agentx.agents`

```python
from agentx.agents import (
    DeepAgent, DeepAgentConfig, DeepAgentResult,
    SubAgentSpec, build_subagent_dispatcher,
    ReflectionConfig, make_planning_tool, make_filesystem_tools, compact_messages,
)

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
result: DeepAgentResult = agent.run()
print(result.summary)
```

| Symbol | What it does |
|---|---|
| `make_planning_tool()` | A no-op `write_todos` tool — forces an explicit, visible task list |
| `make_filesystem_tools(workspace)` | Sandboxed `read_file`/`write_file`/`edit_file`/`list_files` |
| `SubAgentSpec` + `build_subagent_dispatcher(specs)` | A single `task` tool that delegates to named specialist sub-agents (agent-as-tool, isolated context) |
| `ReflectionConfig(enabled, max_revisions)` | Config for an optional critic pass that requests revisions before returning |
| `compact_messages(messages, llm, keep_last=6, token_limit=6000)` | Summarise older messages once the transcript exceeds a token budget |

Backs [`agentx agent deep`](cli/agent.md#agentx-agent-deep). See [Deep agents](features/deep-agents.md).

---

## 4. RAG & embeddings — `agentx.get_embeddings` / `auto_embeddings`

```python
from agentx import (
    get_embeddings, auto_embeddings, EmbeddingConfig,
    HuggingFaceEmbeddingConfig, OpenAIEmbeddingConfig, AzureOpenAIEmbeddingConfig,
    CohereEmbeddingConfig, GoogleEmbeddingConfig, BedrockEmbeddingConfig,
    VoyageEmbeddingConfig, OllamaEmbeddingConfig,
)

# explicit config
emb = get_embeddings(HuggingFaceEmbeddingConfig(model="sentence-transformers/all-MiniLM-L6-v2"))

# or let it pick the best available provider from your installed extras/env vars
emb = auto_embeddings()
vector = emb.embed_query("hello world")
```

8 embedding providers are supported; `HuggingFace` runs fully local (no API key needed). Document
loaders (PDF/Excel/CSV/Word/Markdown) and FAISS/Chroma vector stores live under `agentx.rag` and
are what backs [`agentx rag upload/build/list`](cli/rag.md) in a generated project.

---

## 5. Reliability — retries, fallbacks, budgets, rate limiting

```python
from agentx import (
    build_resilient_chat,
    UsageLimits, UsageTracker, UsageLimitExceeded,
    RateLimiter, rate_limited_callback,
)

# retries + ordered provider/model fallback chain
llm = build_resilient_chat(
    "openai", "gpt-4o-mini",
    fallbacks=[("anthropic", "claude-3-5-sonnet-latest"), ("groq", "llama-3.3-70b-versatile")],
    retries=3,
)

# per-run token/cost/request budget — raises UsageLimitExceeded when hit
limits = UsageLimits(max_requests=50, max_tokens=100_000, max_cost_usd=2.00)
tracker = UsageTracker(limits)
tracker.record(tokens=1200, cost_usd=0.02)

# token-bucket rate limiter (requests/min + tokens/min), usable as a LangChain callback
limiter = RateLimiter(requests_per_minute=60, tokens_per_minute=90_000)
llm_with_limits = get_chat_model("openai", callbacks=[rate_limited_callback(limiter)])
```

`build_resilient_chat` wraps `.with_retry()` + `.with_fallbacks()` around the primary model —
same pattern as pydantic-ai's `FallbackModel`.

---

## 6. Guardrails — `agentx.apply_guards`

```python
from agentx import apply_guards, GuardrailError
from agentx.guardrails import redact_pii, block_banned, enforce_max_length, \
    default_input_guards, default_output_guards

result = apply_guards(user_input, default_input_guards(banned=["ignore previous instructions"]))
if not result.ok:
    raise GuardrailError(result.reason)

safe_output = apply_guards(llm_output, default_output_guards(redact=True)).text
```

| Symbol | What it does |
|---|---|
| `redact_pii(text, kinds=None)` | Redacts emails/phones/SSNs/etc. |
| `block_banned(text, banned)` | Fails if any banned phrase is present |
| `enforce_max_length(text, max_chars)` | Truncates/fails over a length budget |
| `default_input_guards()` / `default_output_guards()` | Sensible pre-built guard chains |
| `apply_guards(text, guards, raise_on_violation=False)` | Runs a guard chain, returns a `GuardResult` |

---

## 7. Structured outputs — `agentx.structured_model`

```python
from agentx import structured_model
from pydantic import BaseModel

class Extraction(BaseModel):
    name: str
    amount: float

model = structured_model(Extraction, provider="openai", model="gpt-4o-mini")
result: Extraction = model.invoke("Invoice: Acme Corp, $532.10")
```

Wraps LangChain's `.with_structured_output(schema)` behind the same provider-agnostic factory as
`get_chat_model`.

---

## 8. Prompt insights — `agentx.analyze_prompt` / `optimize_prompt`

```python
from agentx import analyze_prompt, optimize_prompt, count_tokens, estimate_cost

report = analyze_prompt(prompt_text)     # quality score 0-100 + checklist + suggestions
print(report.score, report.suggestions)

optimized = optimize_prompt(prompt_text, provider="openai", model="gpt-4o-mini")
print(optimized.text, optimized.diff, optimized.rationale)

tokens = count_tokens(prompt_text, model="gpt-4o-mini")
cost = estimate_cost(tokens_in=500, tokens_out=200, provider="openai", model="gpt-4o-mini")
```

This is what powers the [Prompt dashboard](features/dashboard.md)'s quality score, one-click
optimization, and cost estimate — usable directly without the UI.

---

## 9. Response caching — `agentx.enable_caching`

```python
from agentx import enable_caching, disable_caching, cache_stats, clear_cache

enable_caching()                 # all get_chat_model(...) calls are now cached
...
print(cache_stats())             # {'hit_rate': 0.6, 'tokens_saved': 12000, 'est_usd_saved': 0.024, ...}
clear_cache()
disable_caching()
```

SQLite-backed (`.agentx/llm_cache.sqlite`), TTL-capable: `enable_caching(path=..., ttl=3600)`. See
[Response caching](features/caching.md) and [`agentx cache`](cli/cache.md).

---

## 10. Observability — `agentx.setup_tracing` / `get_callbacks`

```python
from agentx import setup_tracing, get_callbacks, telemetry_enabled

setup_tracing("my-service")             # OpenTelemetry GenAI tracing (+ optional Langfuse)
llm = get_chat_model("openai", callbacks=get_callbacks())

if telemetry_enabled():
    ...
```

Opt-out via `AGENTX_TELEMETRY=false`. This is what `--observability` wires into a generated
project's `observability.py`. See [Enterprise pack](features/enterprise.md).

---

## 11. Logging — `agentx.setup_logging` / `get_logger`

```python
from agentx import setup_logging, get_logger

setup_logging(level="INFO", json=True)   # structured JSON logs, quiet third-party loggers
logger = get_logger(__name__)
logger.info("agent started", extra={"goal": goal})
```

---

## 12. Flow / DAG analysis — `agentx.flow`

```python
from agentx.flow import build_static_flow, build_project_flow, trace, get_current_flow
from agentx.flow import render_ascii, render_mermaid, render_json, render_dot
from agentx.flow import register_renderer, get_renderer, available_renderers
from agentx.flow.htmlgen import render_html
```

Backs [`agentx flow`](cli/flow.md) — see [Flow — code as a DAG](features/flow-dag.md) for the
full write-up, including the interactive viewer's edit-in-place feature.

## 13. MCP tools — `agentx.tools.mcp_server`

```python
from agentx.tools.mcp_server import build_mcp_server

mcp = build_mcp_server(
    name="my-tools",
    tools=["web_search", "tts", "knowledge_research", "database"],
    knowledge_root="./knowledge",
    db_path="./data.db",
)
mcp.run()
```

See [MCP tool templates](features/mcp-tools.md) and [MCP connector](features/mcp-connector.md).

---

## Full public API (`import agentx`)

```python
__all__ = [
    "__version__",
    # providers
    "ProviderSpec", "get_chat_model", "get_crewai_llm", "list_providers",
    # logging
    "setup_logging", "get_logger",
    # agents
    "AutonomousAgent", "ResearchAgent", "AgentResult", "ResearchResult",
    # embeddings
    "get_embeddings", "auto_embeddings", "EmbeddingConfig", "AnyEmbeddingConfig",
    "HuggingFaceEmbeddingConfig", "OpenAIEmbeddingConfig", "AzureOpenAIEmbeddingConfig",
    "CohereEmbeddingConfig", "GoogleEmbeddingConfig", "BedrockEmbeddingConfig",
    "VoyageEmbeddingConfig", "OllamaEmbeddingConfig",
    # enterprise runtime
    "setup_tracing", "get_callbacks", "telemetry_enabled", "build_resilient_chat",
    "UsageLimits", "UsageTracker", "UsageLimitExceeded", "RateLimiter", "rate_limited_callback",
    "apply_guards", "GuardrailError", "structured_model",
    # prompt insights
    "analyze_prompt", "optimize_prompt", "count_tokens", "estimate_cost",
    # response caching
    "enable_caching", "disable_caching", "cache_stats", "clear_cache",
]
```

`agentx.agents`, `agentx.flow`, `agentx.tools`, `agentx.rag`, and `agentx.guardrails` each have
their own, deeper surface beyond what's re-exported at the top level — see the sections above for
the parts of each that are documented, or the source under `src/agentx/` for the rest.
