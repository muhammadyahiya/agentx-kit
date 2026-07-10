# Use as a library

AgentX-Kit's building blocks work standalone — you don't need to scaffold a project to use them.

## Why

- **One factory, every provider.** `get_chat_model("bedrock", ...)` or
  `get_chat_model("openrouter", ...)` — same call, lazy imports, install only the extras you use.
- **Two frameworks.** LangChain/LangGraph *and* CrewAI from the same building blocks.
- **Batteries included.** RAG, short/long-term memory, MCP tools, and a skills registry — each
  optional and gracefully degrading.
- **Scaffolder, not a black box.** The generated project is readable, idiomatic code you own,
  pre-wired to your selections, in a fresh `.venv`.

## Chat models

```python
from agentx import get_chat_model, list_providers

llm = get_chat_model("openai", "gpt-4o-mini")
print(llm.invoke("Say hi in 3 words").content)

for spec in list_providers():
    print(spec.id, "→", spec.label)
```

CrewAI:

```python
from agentx import get_crewai_llm
llm = get_crewai_llm("openrouter", "anthropic/claude-3.5-sonnet")
```

## Caching

```python
from agentx import enable_caching, cache_stats
enable_caching()
print(cache_stats())
```

See [Response caching](features/caching.md).

## Deep agent primitives

```python
from agentx.agents import DeepAgent, SubAgentSpec, ReflectionConfig
```

See [Deep agents](features/deep-agents.md).

## Flow / DAG analysis

```python
from agentx.flow import build_static_flow, build_project_flow, trace, get_current_flow
from agentx.flow import render_ascii, render_mermaid, render_json, render_dot
```

See [Flow — code as a DAG](features/flow-dag.md).

## MCP tools

```python
from agentx.tools.mcp_server import build_mcp_server
```

See [MCP tool templates](features/mcp-tools.md).

## Enterprise building blocks

```python
from agentx import (
    setup_tracing, get_callbacks,
    build_resilient_chat,
    UsageLimits, UsageTracker,
    apply_guards, structured_model,
)
```

See [Enterprise pack](features/enterprise.md).
