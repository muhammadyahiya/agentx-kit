# 🧬 AgentX-Kit

[![PyPI](https://img.shields.io/pypi/v/agentx-kit.svg)](https://pypi.org/project/agentx-kit/)
[![Python](https://img.shields.io/pypi/pyversions/agentx-kit.svg)](https://pypi.org/project/agentx-kit/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**A provider-agnostic agentic framework + interactive project scaffolder for LangChain & CrewAI.**

Pick your LLM provider (OpenAI, Azure, OpenRouter, Anthropic, Gemini, Vertex AI,
Bedrock, Groq, Ollama, **HuggingFace, Cohere, Mistral**), choose your framework,
agents, RAG, memory, MCP tools and skills — and AgentX-Kit generates a
**ready-to-run project in its own `uv` virtual environment**.

```bash
pip install "agentx-kit[all]"
agentx new                 # interactive wizard → scaffolds a uv project
```

> The PyPI distribution is **`agentx-kit`**; the import name and CLI are **`agentx`**
> (`pip install agentx-kit` → `import agentx` / `agentx --help`).

## 🚀 60-second walkthrough
```bash
# 1. Install
pip install "agentx-kit[all]"

# 2. See what you can target
agentx providers                      # 9 LLM providers + the env vars each needs

# 3. Scaffold a complete project from one line (no keys needed to generate)
agentx new --yes --name my-bot \
  --provider openai \
  --prompt "You are a support agent that answers from our docs."

# 4. Run it
cd my-bot && cp .env.example .env      # add your API key
uv sync && uv run my-bot

# 5. Tune prompts live (tokens, cost, quality, optimize) — optional UI
pip install "agentx-kit[dashboard]" && agentx dashboard

# 6. Use it from Claude / Copilot / Codex
claude mcp add agentx-kit -- agentx mcp
```
Prefer guided? Just run `agentx new` (interactive wizard) or
`agentx new --enterprise` for the full production stack
(tracing, guardrails, FastAPI, Docker, CI, evals, caching).

### 🧭 Command cheat-sheet
| Command | What it does |
|---|---|
| `agentx new` | Interactive wizard → scaffold a uv project |
| `agentx new --yes [opts]` | Non-interactive scaffold (`--enterprise` for the full pack) |
| `agentx providers` | List LLM providers + required env vars |
| `agentx graph [--format ascii\|mermaid\|json]` | Show a project's agents, tools, and flow |
| `agentx rag upload/build/list` | Manage a project's RAG knowledge base (PDF/Excel/CSV/Word/…) |
| `agentx agent run/research` | Run an autonomous or research agent |
| `agentx prompt list/set/add/remove` | Manage an existing project's prompts (`-d` opens the dashboard) |
| `agentx dashboard` | Prompt observability, optimization & eval UI (`[dashboard]` extra) |
| `agentx cache stats / clear` | Inspect/clear the LLM response cache |
| `agentx mcp` | Run as an MCP server for Claude/Copilot/Codex |
| `agentx mcp --print-config` | Print the client config for those tools |
| `agentx version` | Show the installed version |

### ✨ Highlights
- **12 LLM providers** + a curated **model catalog** (used by the wizard & dashboard).
- **Structured project layout** (new default): generated LangGraph projects are
  organised into `nodes/` (one module per agent), `state/`, `schemas/`,
  `prompts/`, `utils/` (`llm.py`, `tools.py`, `rag.py`, `retriever.py`,
  `embeddings.py`) and `libs/` — a real project you can grow, not one big file.
- **Multi-agent orchestration**: choose **supervisor** (LLM router), **sequential**
  (pipeline), or **parallel** (fan-out + merge) when you have 2+ agents.
- **Sub-agents / swarm** (`--subagents`): attach delegate agents — each with its
  own tools / MCP / web search — to your agents via the *agent-as-tool* pattern.
- **Voice I/O** (`--voice`): local-first Speech-to-Text + Text-to-Speech
  (`faster-whisper` / `edge-tts`, OpenAI cloud fallback) — `agentx.voice`.
- **Claw** (`--claw`): a multi-channel content assistant (LLM intent router +
  a generic `/claw/webhook`) you can point WhatsApp / Telegram / Slack / email at.
- **Streamlit UI** (`--streamlit`): a chat front-end, with mic input & spoken
  replies when voice is enabled.
- **Small/local-model resilient**: models that emit tool calls as JSON text
  (e.g. llama3.2) are handled transparently — no more raw-JSON replies.
- **RAG that actually chunks + embeds**: LangChain splitter, FAISS **or** Chroma,
  8 embedding providers (HuggingFace local needs no key), document loaders for
  PDF / Excel / CSV / Word / Markdown, and incremental re-index via a manifest.
- **Autonomous & research agents** (`agentx agent …`, or `agentx run` / `agentx
  research`) — sandboxed file tools, web search, citations.
- **Domain-aware seeding**: name a project `legal-assistant` (or pass `--domain`)
  and it gets an expert system prompt + a seed knowledge base + RAG on.
- **Dashboard v2**: pick any provider/model, **enter your API key in the UI**,
  run tests with caching, **LLM-judge relevance evals**, and prompt history.
- **`agentx graph`** to see the agent flow; a **VS Code extension** in
  [`integrations/vscode-agentx/`](integrations/vscode-agentx/).
- **Production-hardened**: request timeouts, rate limiter, structured JSON logs,
  input guardrails, health/readiness probes, and quiet third-party logging.

### ▶️ Try the demos (no API keys needed)
```bash
bash examples/demo_local.sh            # verify local setup end-to-end
python examples/demo_mcp.py            # test the Claude/Copilot MCP path (real handshake)
python examples/mcp_toolkit_client.py  # web search / TTS / knowledge / DB tools over MCP
```
See [`examples/`](examples/) for details.

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
7. **MCP tools**? — and if so, which built-in ones your own MCP server exposes
   (web search, text-to-speech, knowledge research, database — see below)
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

## 🛠️ MCP tool templates (web search · TTS · knowledge research · database)
AgentX-Kit ships ready-made **MCP server tools**, importable directly — no
generated project required:

```bash
pip install "agentx-kit[connector,voice]"
```
```python
from agentx.tools.mcp_server import build_mcp_server

mcp = build_mcp_server(
    name="my-tools",
    tools=["web_search", "tts", "knowledge_research", "database"],  # pick any subset
    knowledge_root="./knowledge",   # scanned by knowledge_research (md/txt/pdf/docx/csv/xlsx)
    db_path="./data.db",            # queried (read-only) by database
)
mcp.run()   # stdio MCP server — connect from Claude, a LangChain agent, or your own client
```

| Tool | What it does | Backing |
|---|---|---|
| `web_search` | DuckDuckGo search | `agentx.tools.builtin` |
| `fetch_url` | Safe HTTP(S) GET + HTML strip | `agentx.tools.builtin` |
| `text_to_speech` | Synthesize speech, returns an audio file path | `agentx.voice.tts` (edge-tts/OpenAI/pyttsx3) |
| `knowledge_search` | Keyword search over local documents — no embeddings needed | `agentx.rag.loaders` |
| `run_sql` / `list_tables` | Read-only SQLite queries (rejects non-`SELECT`) | `sqlite3` |

Try it: `python examples/mcp_toolkit_server.py` + `python examples/mcp_toolkit_client.py`.

**Or generate a project with these baked in** — pick "Integrate MCP tools?" in
the wizard (or `agentx new --yes --mcp --mcp-tools web_search,database`) and
the project gets its own `src/<pkg>/mcp/server.py` + a `mcp/client_demo.py`
sample script, already registered in `mcp_servers.json` so the agent(s) can
call these tools too:

```bash
uv run my-bot-mcp-server                        # run your generated MCP server
uv run python -m my_bot.mcp.client_demo          # sample client
```

## 🧩 Editor & assistant integrations
The same connector powers ready-made integrations (see [`integrations/`](integrations/)):

- **VS Code extension** ([`integrations/vscode`](integrations/vscode)) — commands for
  *New Agent Project*, *Open Prompt Dashboard*, *Add Prompt*, *Cache Stats*, and
  *Register MCP Server for Copilot* (writes `.vscode/mcp.json`). Build with `vsce package`.
- **GitHub Copilot** (agent mode) — add the MCP server via `.vscode/mcp.json`:
  ```jsonc
  { "servers": { "agentx-kit": { "command": "agentx", "args": ["mcp"] } } }
  ```
  (the VS Code command above writes this for you), then ask Copilot to build an agent.
- **Claude Code plugin** ([`integrations/claude-plugin`](integrations/claude-plugin)):
  ```text
  /plugin marketplace add muhammadyahiya/agentx-kit
  /plugin install agentx-kit@agentx-kit
  /agentx-kit:new-agent a support agent that answers from our docs and serves an API
  ```
- **Claude Desktop / Codex** — add the connector config from `agentx mcp --print-config`.

## 💾 Response caching (cost & latency saver)
Caching is the top 2026 token-optimization lever. Turn on a **global LLM response
cache** and every provider call is served from a local store on repeat — no code changes:

```python
from agentx import enable_caching, cache_stats
enable_caching()                 # all get_chat_model(...) calls are cached
...
print(cache_stats())             # {'hit_rate': 0.6, 'tokens_saved': 12000, 'est_usd_saved': 0.024, ...}
```
```bash
agentx cache stats               # hit rate + estimated tokens/$ saved
agentx cache clear
```
Generated projects can enable it automatically (it's part of `--enterprise`), and the
**dashboard's Trends tab shows live hit-rate and $ saved**. TTL-capable, SQLite-backed
at `.agentx/llm_cache.sqlite`.

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
| `mcp` | `langchain-mcp-adapters`, `mcp` | MCP client tools + built-in MCP server templates |
| `observability` | `opentelemetry-*`, `openinference-*` | tracing |
| `server` | `fastapi`, `uvicorn` | serving |
| `voice` | `faster-whisper`, `edge-tts`, `pyttsx3` | Speech-to-Text + Text-to-Speech |
| `streamlit` | `streamlit` | Streamlit chat/voice UI |
| `dashboard` | `streamlit`, `tiktoken`, `pandas` | prompt observability dashboard |
| `connector` | `mcp` | MCP server for Claude/Copilot/Codex |
| `all` | everything above | kitchen sink |

See [DESIGN.md](DESIGN.md) for the architecture and [RESEARCH.md](RESEARCH.md) for the competitive analysis behind these features.

## License
MIT
