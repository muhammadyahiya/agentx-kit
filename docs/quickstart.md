# Quickstart

## 1. Install

```bash
pip install "agentx-kit[all]"
```

## 2. See what you can target

```bash
agentx providers
```

Lists every supported LLM provider id and the environment variables it needs.

## 3. Scaffold a project

Interactive (recommended the first time):

```bash
agentx new
```

The wizard walks through, one option at a time:

1. Project name & target directory
2. Framework — **LangGraph** or **CrewAI**
3. LLM **provider** and **model**
4. Number of **agents** (and their roles)
5. **RAG** module? (vector store)
6. **Memory**? (short-term / long-term / both)
7. **MCP tools**? — and if so, which built-in ones your own MCP server exposes
8. **Skills** integration?
9. **Prompt** style (defaults or scaffolded custom prompts)
10. Create `.venv` and `uv sync` now?

Or non-interactive, for scripting/CI:

```bash
agentx new --yes --name my-bot \
  --provider openai \
  --prompt "You are a support agent that answers from our docs."
```

## 4. Run it

```bash
cd my-bot
cp .env.example .env      # add your API key
uv sync && uv run my-bot
```

## 5. Tune prompts live (optional)

```bash
pip install "agentx-kit[dashboard]"
agentx dashboard
```

Opens a Streamlit workbench at `http://localhost:8501` with token/cost/quality scoring, one-click
optimization, and test runs. See [Prompt dashboard](features/dashboard.md).

## 6. Use it from Claude / Copilot / Codex

```bash
claude mcp add agentx-kit -- agentx mcp
```

Now you can ask your assistant, in plain language, to build a project — see
[MCP connector](features/mcp-connector.md).

## Where next

- Want the full production stack in one flag? `agentx new --enterprise` — see
  [Enterprise pack](features/enterprise.md).
- Want to see your code as an interactive graph? `agentx flow --ui` — see
  [Flow — code as a DAG](features/flow-dag.md).
- Want every flag documented? Head to the [CLI Reference](cli/index.md).
