# `agentx new`

Scaffold a new agentic project. Interactive by default; fully scriptable with `--yes`.

```bash
agentx new
```

## Interactive wizard

Run with no flags and answer one question at a time:

1. Project name & target directory
2. Framework — **LangGraph** or **CrewAI**
3. LLM **provider** and **model**
4. Number of **agents** (and their roles)
5. **RAG** module? (vector store)
6. **Memory**? (short-term / long-term / both)
7. **MCP tools**? — and if so, which built-in ones
8. **Skills** integration?
9. **Prompt** style (defaults or scaffolded custom prompts)
10. Create `.venv` and `uv sync` now?

## Non-interactive (`--yes`)

```bash
agentx new --yes --name my-bot \
  --provider openai \
  --prompt "You are a support agent that answers from our docs."
```

## Options

| Flag | Description |
|---|---|
| `-n, --name TEXT` | Project name |
| `-o, --out PATH` | Target directory (default `./<name>`) |
| `-y, --yes` | Non-interactive: use defaults + options below |
| `--framework TEXT` | `langgraph` \| `crewai` (default `langgraph`) |
| `--provider TEXT` | Provider id (default `openai`) — see [Providers](../providers.md) |
| `--model TEXT` | Model id (blank = provider default) |
| `--agents INTEGER` | Number of agents (default `1`) |
| `--agent-mode TEXT` | `chat` \| `autonomous` \| `research` \| `deep` (default `chat`) |
| `--deep-planning / --no-deep-planning` | Deep mode: `write_todos` planning tool (default on) |
| `--deep-filesystem / --no-deep-filesystem` | Deep mode: sandboxed filesystem tools (default on) |
| `--deep-reflection` | Deep mode: critic/reflection revision loop |
| `--orchestration TEXT` | `supervisor` \| `sequential` \| `parallel` (LangGraph, >1 agents; default `supervisor`) |
| `-p, --prompt TEXT` | System prompt for the first agent |
| `--role TEXT` | Role for the first agent (default `Helpful Assistant`) |
| `--goal TEXT` | Goal for the first agent |
| `--rag / --no-rag` | Include RAG (default off) |
| `--domain TEXT` | Domain seed: `''` auto-infer, `'none'` generic, or `legal\|medical\|finance\|...` |
| `--problem TEXT` | Problem statement — used to infer the domain |
| `--memory TEXT` | `none` \| `short` \| `long` \| `both` (default `none`) |
| `--mcp / --no-mcp` | Include MCP tools (default off) |
| `--mcp-tools TEXT` | Comma-separated subset of `web_search,tts,knowledge_research,database` |
| `--skills / --no-skills` | Include skills registry (default off) |
| `--subagents / --no-subagents` | Attach sub-agents/swarm (default off) |
| `--voice / --no-voice` | Add voice I/O — STT + TTS (default off) |
| `--streamlit / --no-streamlit` | Generate a Streamlit UI (default off) |
| `--claw / --no-claw` | Add the Claw multi-channel assistant (default off) |
| `--enterprise` | Enable the full enterprise pack (tracing, guardrails, FastAPI, Docker, CI, evals) |
| `--observability / --no-observability` | OpenTelemetry/Langfuse observability (default off) |
| `--guardrails / --no-guardrails` | Input/output guardrails (default off) |
| `--serve / --no-serve` | FastAPI server (REST + SSE) (default off) |
| `--docker / --no-docker` | Dockerfile + docker-compose (default off) |
| `--ci / --no-ci` | GitHub Actions CI (default off) |
| `--evals / --no-evals` | LLM-as-judge eval harness (default off) |
| `--no-venv` | Do not create a `.venv` |
| `--sync` | Run `uv sync` after generating |
| `--overwrite / --no-overwrite` | Overwrite a non-empty target directory |
| `--list-frameworks` | Print valid `--framework` choices and exit |
| `--list-providers` | Print valid `--provider` ids and exit |
| `-q, --quiet` | Suppress the human-readable result panel (for CI/scripts) |
| `--json` | Print a one-line JSON summary instead of the Rich panel (implies `--quiet`) |

## Examples

Minimal chat agent, OpenAI:

```bash
agentx new --yes -n support-bot --provider openai \
  --prompt "You are a support agent that answers from our docs."
```

Multi-agent LangGraph project with a supervisor:

```bash
agentx new --yes -n research-team --agents 3 --orchestration supervisor \
  --provider anthropic --model claude-sonnet-4-6
```

RAG-enabled assistant with memory:

```bash
agentx new --yes -n docs-bot --rag --memory long --provider openai
```

CrewAI crew with MCP tools baked in:

```bash
agentx new --yes -n crew-bot --framework crewai --mcp \
  --mcp-tools web_search,database
```

Deep agent with reflection:

```bash
agentx new --yes -n auditor --agent-mode deep --deep-reflection \
  --prompt "You audit codebases for security issues."
```

Full production stack in one flag:

```bash
agentx new --yes -n my-bot --enterprise
```

Domain-aware seeding (auto-detected from the name, or explicit):

```bash
agentx new --yes -n legal-assistant                       # auto-infers "legal" domain
agentx new --yes -n my-bot --domain medical --rag          # explicit domain + RAG
```

Discover valid ids before scripting:

```bash
agentx new --list-frameworks
agentx new --list-providers
```

CI/scripting-friendly output:

```bash
agentx new --yes -n ci-bot --json > result.json
```

## After generation

```bash
cd my-bot
cp .env.example .env      # add your API key
uv sync && uv run my-bot
```
