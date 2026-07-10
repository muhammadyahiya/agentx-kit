# Enterprise pack

Generate a production-shaped project with one flag — informed by a survey of
CrewAI/LangGraph/create-llama/AgentStack/agno/pydantic-ai (see
[RESEARCH.md](https://github.com/muhammadyahiya/agentx-kit/blob/main/RESEARCH.md)):

```bash
agentx new --yes -n my-bot --enterprise        # everything below
# or pick individually:
agentx new --yes -n my-bot --observability --guardrails --serve --docker --ci --evals
```

## What `--enterprise` adds to the generated project

- **Observability** — OpenTelemetry GenAI tracing + optional Langfuse (`observability.py`),
  opt-out via `AGENTX_TELEMETRY=false`.
- **Guardrails** — input/output validation + PII redaction (`guardrails.py`).
- **FastAPI server** — `server.py` with `/health`, `/chat`, and SSE `/chat/stream`.
- **Docker** — `Dockerfile` + `docker-compose.yml` (+ `.dockerignore`).
- **CI** — `.github/workflows/ci.yml` (lint + compile + tests, optional eval gate).
- **Evals** — `evals/` LLM-as-judge harness runnable locally and in CI.
- **Typed config** — `config.py` via `pydantic-settings` (12-factor).
- **Manifest** — `agentx.json` declaring framework, provider, features (à la `langgraph.json`).

## Use the same building blocks as a library

```python
from agentx import (
    setup_tracing, get_callbacks,          # observability
    build_resilient_chat,                  # retries + provider fallbacks
    UsageLimits, UsageTracker,             # token/cost budgets
    apply_guards, structured_model,        # guardrails + typed outputs
)
setup_tracing("my-service")
llm = build_resilient_chat("openai", "gpt-4o-mini", fallbacks=[("anthropic", "claude-3-5-sonnet-latest")])
```

See [`agentx new`](../cli/new.md) for the individual flags this pack expands to.
