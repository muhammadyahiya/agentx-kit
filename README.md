# 🧬 AgentX-Kit

[![PyPI](https://img.shields.io/pypi/v/agentx-kit.svg)](https://pypi.org/project/agentx-kit/)
[![Python](https://img.shields.io/pypi/pyversions/agentx-kit.svg)](https://pypi.org/project/agentx-kit/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**A provider-agnostic agentic framework + interactive project scaffolder for LangChain & CrewAI.**

Pick your LLM provider (OpenAI, Azure, OpenRouter, Anthropic, Gemini, Vertex AI,
Bedrock, Groq, Ollama), choose your framework, agents, RAG, memory, MCP tools and
skills — and AgentX-Kit generates a **ready-to-run project in its own `uv`
virtual environment**.

```bash
pip install "agentx-kit[all]"
agentx new                 # interactive wizard → scaffolds a uv project
```

> The PyPI distribution is **`agentx-kit`**; the import name and CLI are **`agentx`**
> (`pip install agentx-kit` → `import agentx` / `agentx --help`).

## 📦 Installation

### From PyPI (recommended)
```bash
pip install agentx-kit                 # core: CLI + scaffolder + base abstractions
pip install "agentx-kit[all]"          # everything
```
Each LLM provider is an **optional extra** so you only pull the SDKs you use:
```bash
pip install "agentx-kit[openai,langgraph]"        # OpenAI + LangGraph
pip install "agentx-kit[bedrock,crewai,rag,mcp]"  # Bedrock + CrewAI + RAG + MCP
```

### Using `uv`
```bash
uv pip install "agentx-kit[all]"
```

### From GitHub (latest, unreleased)
```bash
pip install "agentx-kit[all] @ git+https://github.com/muhammadyahiya/agentx-kit.git"
```

### From a local clone (development)
```bash
git clone https://github.com/muhammadyahiya/agentx-kit.git
cd agentx-kit
uv venv && uv pip install -e ".[all,dev]"   # or: pip install -e ".[all,dev]"
pytest -q
```

> Requires **Python 3.10–3.13** and (for the scaffolder's `.venv` creation)
> [`uv`](https://docs.astral.sh/uv/).

### Verify
```bash
agentx version
agentx providers     # lists every provider + the env vars it needs
```

## Why
- **One factory, every provider.** `get_chat_model("bedrock", ...)` or
  `get_chat_model("openrouter", ...)` — same call, lazy imports, install only
  the extras you use.
- **Two frameworks.** LangChain/LangGraph *and* CrewAI from the same building blocks.
- **Batteries included.** RAG, short/long-term memory, MCP tools, and a skills
  registry — each optional and gracefully degrading.
- **Scaffolder, not a black box.** The generated project is readable, idiomatic
  code you own, pre-wired to your selections, in a fresh `.venv`.

## Use as a library
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

## Scaffold a project
```bash
agentx new                         # fully interactive
agentx new --name my-bot --yes     # accept sensible defaults
agentx providers                   # list providers + required env vars
```

The wizard asks, one option at a time:

1. Project name & target directory
2. Framework — **LangGraph** or **CrewAI**
3. LLM **provider** and **model**
4. Number of **agents** (and their roles)
5. **RAG** module? (vector store)
6. **Memory**? (short-term / long-term / both)
7. **MCP tools**?
8. **Skills** integration?
9. **Prompt** style (defaults or scaffolded custom prompts)
10. Create `.venv` and `uv sync` now?

It then renders the project, writes a feature-aware `pyproject.toml` + `.env.example`,
and runs `uv venv` to create `.venv`.

## Prompts: add at creation, or any time after
Prompts are **not baked into code** — every generated project keeps them in a
`prompts.json` that `agents.py` loads dynamically. Add an entry and the project
runs it on next start, **no code changes**.

```bash
# at creation
agentx new --yes -n chatops --prompt "You are a senior DevOps engineer. Be terse."

# after creation (run inside the project)
agentx prompt list
agentx prompt set assistant --text "You are an SRE. Prioritise reliability."
agentx prompt add reviewer --role "Code Reviewer" --goal "Review diffs" \
    --text "You review code for bugs and security."
agentx prompt remove reviewer
```

`prompts.json`:
```json
{
  "with_rag": false,
  "agents": {
    "assistant": {"role": "...", "goal": "...", "system_prompt": "You are ..."}
  }
}
```
A blank `system_prompt` is auto-derived from the agent's role + goal. You can also
just open `prompts.json` in an editor — the CLI is a convenience, not a gate.

## 📊 Prompt dashboard (observability + optimization)
A Streamlit workbench to **understand and refine how your prompts talk to the LLM** —
launch it any time:

```bash
pip install "agentx-kit[dashboard]"
agentx dashboard                 # opens http://localhost:8501
agentx prompt set assistant -d   # edit a prompt AND open the dashboard
```

It gives you, live as you edit:
- **Token count, context-window utilization gauge, and cost estimate** (tiktoken-accurate).
- **Quality score (0–100)** with a checklist (role / goal / output-format / examples / constraints / specificity) and **concrete suggestions + limit warnings**.
- **✨ One-click LLM optimization** — refines the prompt while preserving intent, shows a **diff + rationale + token delta**, and can **apply the result straight back to `prompts.json`**.
- **▶️ Test run** — send the prompt to the model and see the response with **tokens in/out, latency, and cost**.
- **📈 Usage trends** — tokens, cost, and latency over time, logged locally to `.agentx/insights.jsonl`.

Run it inside a generated AgentX project and it reads/writes that project's
`prompts.json`; run it anywhere else for a free-form prompt scratchpad.

## 🔌 Use as a connector (Claude / Copilot / Codex)
AgentX-Kit ships an **MCP server**, so any MCP-capable assistant can scaffold a
complete project from **a single prompt with your problem statement**.

```bash
pip install "agentx-kit[connector]"
agentx mcp --print-config        # prints the client config below
```

Add it to your client (then restart it):
```jsonc
// Claude Desktop / Codex / Copilot — under "mcpServers"
{ "mcpServers": { "agentx-kit": { "command": "agentx", "args": ["mcp"] } } }
```
```bash
# Claude Code one-liner
claude mcp add agentx-kit -- agentx mcp
```

Now just ask, in plain language:
> *“Build a customer-support agent that answers from our product docs and serves a REST API.”*

The assistant calls AgentX-Kit's tools and you get a complete, runnable project:
- **`recommend_project(problem_statement)`** — suggests framework, provider, agent count, and features.
- **`create_agent_project(problem_statement, …)`** — generates the project (infers RAG/serve/memory/etc. from the statement, or take explicit overrides / `enterprise=true`) and returns the file tree + key file contents + run steps.
- **`list_providers`**, **`analyze_prompt`**, **`optimize_prompt`** — provider list + prompt insights.

So from one sentence the assistant produces a pre-wired project (prompts already seeded from your use case), ready to `uv sync && uv run`.

## 🏢 Enterprise pack
Generate a production-shaped project with one flag — informed by a survey of
CrewAI/LangGraph/create-llama/AgentStack/agno/pydantic-ai (see [RESEARCH.md](RESEARCH.md)):

```bash
agentx new --yes -n my-bot --enterprise        # everything below
# or pick individually:
agentx new --yes -n my-bot --observability --guardrails --serve --docker --ci --evals
```

What `--enterprise` adds to the generated project:
- **Observability** — OpenTelemetry GenAI tracing + optional Langfuse (`observability.py`), opt-out via `AGENTX_TELEMETRY=false`.
- **Guardrails** — input/output validation + PII redaction (`guardrails.py`).
- **FastAPI server** — `server.py` with `/health`, `/chat`, and SSE `/chat/stream`.
- **Docker** — `Dockerfile` + `docker-compose.yml` (+ `.dockerignore`).
- **CI** — `.github/workflows/ci.yml` (lint + compile + tests, optional eval gate).
- **Evals** — `evals/` LLM-as-judge harness runnable locally and in CI.
- **Typed config** — `config.py` via `pydantic-settings` (12-factor).
- **Manifest** — `agentx.json` declaring framework, provider, features (à la `langgraph.json`).

These are also usable as a **library** in any project:
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

## Installation extras
| Extra | Installs | For |
|---|---|---|
| `openai` / `azure` / `openrouter` | `langchain-openai` | OpenAI-compatible |
| `anthropic` | `langchain-anthropic` | Claude |
| `google` | `langchain-google-genai` | Gemini (AI Studio) |
| `vertex` | `langchain-google-vertexai` | Vertex AI |
| `bedrock` | `langchain-aws` | Amazon Bedrock |
| `groq` | `langchain-groq` | Groq |
| `ollama` | `langchain-ollama` | local |
| `langgraph` | `langgraph`, `langchain` | LangGraph agents |
| `crewai` | `crewai` | CrewAI crews |
| `rag` | `langchain-community`, `chromadb` | RAG |
| `mcp` | `langchain-mcp-adapters` | MCP tools |
| `observability` | `opentelemetry-*`, `openinference-*` | tracing |
| `server` | `fastapi`, `uvicorn` | serving |
| `dashboard` | `streamlit`, `tiktoken`, `pandas` | prompt observability dashboard |
| `connector` | `mcp` | MCP server for Claude/Copilot/Codex |
| `all` | everything above | kitchen sink |

See [DESIGN.md](DESIGN.md) for the architecture and [RESEARCH.md](RESEARCH.md) for the competitive analysis behind these features.

## License
MIT
