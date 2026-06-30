# 🧬 AgentX

**A provider-agnostic agentic framework + interactive project scaffolder for LangChain & CrewAI.**

Pick your LLM provider (OpenAI, Azure, OpenRouter, Anthropic, Gemini, Vertex AI,
Bedrock, Groq, Ollama), choose your framework, agents, RAG, memory, MCP tools and
skills — and AgentX generates a **ready-to-run project in its own `uv`
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
pip install "agentx-kit[all] @ git+https://github.com/muhammadyahiya/agentx.git"
```

### From a local clone (development)
```bash
git clone https://github.com/muhammadyahiya/agentx.git
cd agentx
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
| `all` | everything above | kitchen sink |

See [DESIGN.md](DESIGN.md) for the architecture.

## License
MIT
