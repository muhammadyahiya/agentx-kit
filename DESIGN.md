# AgentX — High-Level Design

AgentX is two things in one package:

1. **A provider-agnostic agentic runtime library** (`agentx`) — a thin, batteries-included layer over **LangChain/LangGraph** and **CrewAI** that lets you talk to *any* LLM provider through one factory, and compose RAG, memory, MCP tools and skills.
2. **An interactive project scaffolder** (`agentx new`) — a runtime wizard that asks you, one option at a time, which framework, provider, agents, RAG, memory, MCP and skills you want, then generates a **ready-to-run project in its own `uv` virtual environment (`.venv`)**.

The generated project depends on `agentx` and is a working template you can run immediately.

```
┌─────────────────────────────────────────────────────────────────────┐
│                            agentx (CLI)                                 │
│   agentx new   │   agentx providers   │   agentx version                    │
└───────────────┬───────────────────────────────────────────────┬──────┘
                │                                                 │
        ┌───────▼─────────┐                              ┌────────▼────────┐
        │  scaffold/      │  interactive wizard ──────►  │   generator     │
        │  wizard.py      │  collects a ProjectSpec      │  renders Jinja  │
        │  spec.py        │                              │  + `uv venv`    │
        └─────────────────┘                              └────────┬────────┘
                                                                   │ writes
                                                                   ▼
                                                   ┌───────────────────────────┐
                                                   │  generated project (.venv) │
                                                   │  main.py, agents.py, ...   │
                                                   │  imports agentx        │
                                                   └───────────────────────────┘

        ── runtime library (imported by generated projects) ──
        providers/  frameworks/  rag/  memory/  tools/  skills/  prompts/
```

## 1. Provider layer (`agentx/providers`)

The crown jewel. A **registry** maps a provider id → a `ProviderSpec` describing:
its display name, the pip extra to install, the env vars it needs, a sensible
default model, and how to build a model object for **both** frameworks.

| Provider id  | LangChain class                         | CrewAI model prefix     | Key env vars |
|--------------|------------------------------------------|--------------------------|--------------|
| `openai`     | `langchain_openai.ChatOpenAI`            | `openai/…`               | `OPENAI_API_KEY` |
| `azure`      | `langchain_openai.AzureChatOpenAI`       | `azure/…`                | `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT` |
| `openrouter` | `ChatOpenAI` (base_url=openrouter)       | `openrouter/…`           | `OPENROUTER_API_KEY` |
| `anthropic`  | `langchain_anthropic.ChatAnthropic`      | `anthropic/…`            | `ANTHROPIC_API_KEY` |
| `gemini`     | `langchain_google_genai.ChatGoogleGenerativeAI` | `gemini/…`        | `GOOGLE_API_KEY` |
| `vertexai`   | `langchain_google_vertexai.ChatVertexAI` | `vertex_ai/…`            | `GOOGLE_APPLICATION_CREDENTIALS`, `GOOGLE_CLOUD_PROJECT` |
| `bedrock`    | `langchain_aws.ChatBedrockConverse`      | `bedrock/…`              | `AWS_*` / profile |
| `groq`       | `langchain_groq.ChatGroq`                | `groq/…`                 | `GROQ_API_KEY` |
| `ollama`     | `langchain_ollama.ChatOllama`            | `ollama/…` (+ base_url)  | — (local) |

Two factory functions:
- `get_chat_model(provider, model=None, **kw) -> BaseChatModel` (LangChain/LangGraph).
- `get_crewai_llm(provider, model=None, **kw) -> crewai.LLM` (CrewAI; routes via LiteLLM).

Imports are **lazy** — installing `agentx-kit[openai]` only is enough to use OpenAI; nothing else is imported until requested. A clear error tells you the exact extra to install.

## 2. Frameworks (`agentx/frameworks`)

- **LangGraph adapter** — `build_react_agent(...)` / a small `StateGraph` runner that wires a chat model + tools + memory into a runnable agent. Multi-agent = a graph of nodes.
- **CrewAI adapter** — `build_agent(...)`, `build_crew(...)` helpers that accept the same provider/tool/memory inputs and return CrewAI `Agent`/`Crew` objects.

Both consume the same building blocks so a project can switch frameworks with minimal change.

## 3. Capabilities (optional, lazy)

- **RAG** (`rag/`) — document loaders → `RecursiveCharacterTextSplitter` → vector store (Chroma, or an offline keyword fallback) → retriever. Exposed as a tool.
- **Memory** (`memory/`) — short-term (windowed buffer) + long-term (persistent JSONL/SQLite) conversation memory.
- **Tools / MCP** (`tools/`) — `load_mcp_tools(config)` via `langchain-mcp-adapters`; plus built-in tools (web search).
- **Skills** (`skills/`) — a filesystem-backed skill registry whose instructions are injected into prompts (and optionally exposed as a lookup tool).
- **Prompts** (`prompts/`) — reusable, override-able prompt templates.

Every capability degrades gracefully: if its extra isn't installed, the feature is disabled with a helpful message rather than crashing.

## 4. Scaffolder (`agentx/scaffold`)

- `ProjectSpec` (pydantic) is the single source of truth for a generation run.
- `wizard.py` collects it interactively (`questionary`), **one option at a time**:
  project name → framework → provider → model → number & roles of agents →
  RAG? → memory? → MCP? → skills? → prompt style → run `uv sync`?
- `generator.py` renders **Jinja2 templates** into the target directory, writes a
  provider/feature-aware `pyproject.toml` and `.env.example`, then runs
  `uv venv` to create `.venv` (and optionally `uv sync`).
- A programmatic `generate_project(spec, target_dir)` API makes the whole thing
  testable and usable from other scripts (no TTY required).

### Prompts are data, not code
Every generated project is **prompt-file driven**: agent prompts live in a
`prompts.json` that the generated `prompts.py` / `agents.py` load at runtime, and
`build_agents()` iterates over that file. So adding an agent/prompt — at creation
(`agentx new --prompt`) or afterward (`agentx prompt add|set|remove`, or editing the
file) — changes the running project **without touching code**. `prompts_store.py`
provides the safe read/modify/write helpers the CLI uses.

## Design principles
- **Provider-agnostic core, lazy provider imports** — install only what you use.
- **One spec, two surfaces** — the same `ProjectSpec` drives interactive and programmatic generation.
- **Generated code is readable** — templates produce idiomatic, commented code, not a black box.
- **Graceful degradation** — optional capabilities never hard-crash the import.
