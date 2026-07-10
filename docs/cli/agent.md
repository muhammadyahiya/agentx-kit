# `agentx agent`

Run autonomous and research agents **standalone** — no generated project required.

```bash
agentx agent --help
```

| Subcommand | Purpose |
|---|---|
| `agentx agent run` | Run an autonomous agent towards a goal |
| `agentx agent research` | Run a research agent that produces a sourced report |
| `agentx agent deep` | Run a deep agent: planning + filesystem + optional reflection loop |

## `agentx agent run`

The agent plans, searches the web, reads/writes files, and works until it reaches the goal or
hits the iteration cap.

| Flag | Description |
|---|---|
| `GOAL` | Goal for the autonomous agent (required) |
| `-p, --provider TEXT` | Default `openai` |
| `-m, --model TEXT` | Model id |
| `-w, --workspace PATH` | Default `workspace` |
| `--max-iter INTEGER` | Default `20` |
| `--allow-shell` | Allow shell command execution |

```bash
agentx agent run "Research the top 5 RAG frameworks and write a report"
agentx agent run "Refactor utils.py for readability" -w ./project --allow-shell
```

## `agentx agent research`

| Flag | Description |
|---|---|
| `TOPIC` | Research topic or question (required) |
| `-p, --provider TEXT` | Default `openai` |
| `-m, --model TEXT` | Model id |
| `-d, --depth TEXT` | `quick` \| `standard` \| `deep` (default `standard`) |
| `-o, --output PATH` | Save report to this file |

```bash
agentx agent research "LLM inference optimisation 2025" --depth deep -o report.md
agentx agent research "State of vector databases" --provider anthropic
```

## `agentx agent deep`

Planning + filesystem tools + an optional critic/reflection revision loop — the same primitives
behind LangChain's `deepagents` and Claude Code's own harness.

| Flag | Description |
|---|---|
| `GOAL` | Goal for the deep agent (required) |
| `-p, --provider TEXT` | Default `openai` |
| `-m, --model TEXT` | Model id |
| `-w, --workspace PATH` | Default `workspace` |
| `--max-iter INTEGER` | Default `25` |
| `--planning / --no-planning` | Give it a `write_todos` planning tool (default: on) |
| `--filesystem / --no-filesystem` | Give it sandboxed file tools (default: on) |
| `--reflection` | Add a critic/reflection revision loop |
| `--max-revisions INTEGER` | Default `2` |

```bash
agentx agent deep "Audit this repo's error handling and write a report."
agentx agent deep "Refactor the auth module" --reflection --max-revisions 3
```

## As a library

```python
from agentx.agents import DeepAgent, SubAgentSpec, ReflectionConfig

agent = DeepAgent.create(
    goal="Audit this repo's error handling and write a report.",
    provider="openai",
    workspace="./workspace",
    subagents=[
        SubAgentSpec(name="reviewer", description="Reviews code for bugs.",
                     prompt="You are a meticulous code reviewer."),
    ],
    reflection=ReflectionConfig(enabled=True, max_revisions=2),
)
result = agent.run()
print(result.summary)
```

| Building block | What it does |
|---|---|
| `make_planning_tool()` | A no-op `write_todos` tool — forces an explicit, visible task list |
| `make_filesystem_tools(workspace)` | Sandboxed `read_file`/`write_file`/`edit_file`/`list_files` |
| `SubAgentSpec` + `build_subagent_dispatcher(...)` | A single `task` tool that delegates to named specialist sub-agents |
| `ReflectionConfig` + `run_with_reflection(...)` | An optional critic pass that requests revisions before returning |
| `compact_messages(...)` | Summarise older messages once the transcript exceeds a token budget |

See [Deep agents](../features/deep-agents.md) for the full write-up, including how to bake one
into a generated project.
