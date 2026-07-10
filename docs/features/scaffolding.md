# Project scaffolding

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
7. **MCP tools**? — and if so, which built-in ones your own MCP server exposes (web search,
   text-to-speech, knowledge research, database)
8. **Skills** integration?
9. **Prompt** style (defaults or scaffolded custom prompts)
10. Create `.venv` and `uv sync` now?

It then renders the project, writes a feature-aware `pyproject.toml` + `.env.example`, and runs
`uv venv` to create `.venv`.

## Structured project layout

Generated LangGraph projects are organised into:

- `nodes/` — one module per agent
- `state/` — graph state definitions
- `schemas/` — Pydantic models
- `prompts/` — prompt loading (backed by `prompts.json`)
- `utils/` — `llm.py`, `tools.py`, `rag.py`, `retriever.py`, `embeddings.py`
- `libs/` — shared library code

A real project you can grow, not one big file.

## Multi-agent orchestration

With 2+ agents (LangGraph), choose how they connect via `--orchestration`:

- **supervisor** — an LLM router dispatches to the right agent
- **sequential** — a fixed pipeline, agent A → B → C
- **parallel** — fan-out to all agents, then merge results

```bash
agentx new --yes -n research-team --agents 3 --orchestration supervisor
```

## Sub-agents / swarm

`--subagents` attaches delegate agents — each with its own tools / MCP / web search — to your
agents via the *agent-as-tool* pattern.

## Domain-aware seeding

Name a project `legal-assistant` (or pass `--domain`) and it gets an expert system prompt + a seed
knowledge base + RAG turned on automatically:

```bash
agentx new --yes -n legal-assistant             # auto-infers "legal"
agentx new --yes -n my-bot --domain medical --rag
```

See [`agentx new`](../cli/new.md) for the full flag reference.
