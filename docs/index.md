# AgentX-Kit

**A provider-agnostic agentic framework + interactive project scaffolder for LangChain & CrewAI.**

Pick your LLM provider (OpenAI, Azure, OpenRouter, Anthropic, Gemini, Vertex AI, Bedrock, Groq,
Ollama, HuggingFace, Cohere, Mistral), choose your framework, agents, RAG, memory, MCP tools and
skills — and AgentX-Kit generates a **ready-to-run project in its own `uv` virtual environment**.

```bash
pip install "agentx-kit[all]"
agentx new                 # interactive wizard → scaffolds a uv project
```

!!! note "Package name vs. import name"
    The PyPI distribution is **`agentx-kit`**; the import name and CLI are **`agentx`**
    (`pip install agentx-kit` → `import agentx` / `agentx --help`).

## 60-second walkthrough

```bash
# 1. Install
pip install "agentx-kit[all]"

# 2. See what you can target
agentx providers                      # 12 LLM providers + the env vars each needs

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

Prefer guided? Just run `agentx new` (interactive wizard) or `agentx new --enterprise` for the
full production stack (tracing, guardrails, FastAPI, Docker, CI, evals, caching).

## Command cheat-sheet

| Command | What it does |
|---|---|
| [`agentx new`](cli/new.md) | Interactive wizard → scaffold a uv project |
| [`agentx new --yes [opts]`](cli/new.md) | Non-interactive scaffold (`--enterprise` for the full pack) |
| [`agentx validate`](cli/validate.md) | Check a generated project's `agentx.json` for structural issues |
| [`agentx upgrade`](cli/upgrade.md) | Re-run the current agentx-kit's templates over an existing project |
| [`agentx providers`](cli/misc.md) | List LLM providers + required env vars |
| [`agentx graph`](cli/graph.md) | Show a project's agents, tools, and flow |
| [`agentx flow`](cli/flow.md) | Function-call DAG for a file or whole project — static, live, interactive |
| [`agentx rag upload/build/list`](cli/rag.md) | Manage a project's RAG knowledge base |
| [`agentx agent run/research/deep`](cli/agent.md) | Run an autonomous, research, or deep agent |
| [`agentx prompt list/set/add/remove`](cli/prompt.md) | Manage an existing project's prompts |
| [`agentx dashboard`](cli/dashboard.md) | Prompt observability, optimization & eval UI |
| [`agentx cache stats/clear`](cli/cache.md) | Inspect/clear the LLM response cache |
| [`agentx mcp`](cli/mcp.md) | Run as an MCP server for Claude/Copilot/Codex |
| [`agentx version`](cli/misc.md) | Show the installed version |

## Highlights

- **12 LLM providers** + a curated model catalog (used by the wizard & dashboard).
- **Structured project layout**: generated LangGraph projects are organised into `nodes/`,
  `state/`, `schemas/`, `prompts/`, `utils/`, and `libs/` — a real project you can grow.
- **Multi-agent orchestration**: supervisor (LLM router), sequential (pipeline), or parallel
  (fan-out + merge).
- **Sub-agents / swarm**: attach delegate agents via the agent-as-tool pattern.
- **Voice I/O**: local-first Speech-to-Text + Text-to-Speech.
- **Claw**: a multi-channel content assistant (WhatsApp / Telegram / Slack / email).
- **Streamlit UI**: a chat front-end with mic input & spoken replies.
- **RAG that actually chunks + embeds**: FAISS or Chroma, 8 embedding providers, PDF/Excel/CSV/
  Word/Markdown loaders, incremental re-index.
- **Autonomous & research agents** — sandboxed file tools, web search, citations.
- **Deep agents** — planning tool, sandboxed filesystem tools, sub-agent delegation, optional
  critic/reflection loop.
- **Flow — code as a DAG** — static AST call graph or `--live` runtime trace, with an interactive
  2D/3D viewer you can now [edit code from directly](features/flow-dag.md#edit-in-place).
- **Domain-aware seeding** — name a project `legal-assistant` and it gets an expert system prompt
  + a seed knowledge base + RAG on.
- **Production-hardened** — request timeouts, rate limiter, structured JSON logs, guardrails,
  health/readiness probes.

## Where to go next

<div class="grid cards" markdown>

- **[Installation](installation.md)** — pip/uv, extras, verifying the install
- **[Quickstart](quickstart.md)** — your first project end to end
- **[CLI Reference](cli/index.md)** — every command, every flag, with examples
- **[Features](features/scaffolding.md)** — deep dives on RAG, deep agents, flow, caching, MCP
- **[Library usage](library-usage.md)** — use AgentX-Kit's building blocks directly in your code

</div>
