# Deep agents (planning · filesystem · sub-agents · reflection)

AgentX-Kit ships the same primitives behind LangChain's `deepagents` and Claude Code's own coding
harness — usable directly as a library, via the CLI, or baked into a generated project.

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
| `SubAgentSpec` + `build_subagent_dispatcher(...)` | A single `task` tool that delegates to named specialist sub-agents (agent-as-tool, isolated context) |
| `ReflectionConfig` + `run_with_reflection(...)` | An optional critic pass that requests revisions before returning |
| `compact_messages(...)` | Summarise older messages once the transcript exceeds a token budget |

## From the CLI

```bash
agentx agent deep "Audit this repo's error handling and write a report." --reflection
```

See [`agentx agent`](../cli/agent.md) for the full flag reference.

## Or generate a project with a deep agent baked in

Pick "Deep" as the agent mode in the wizard (or `agentx new --yes --agent-mode deep`) and the
generated `nodes/agent.py` uses `make_deep_agent_node(...)` instead of the default chat node, with
planning/filesystem/reflection wired per your choices:

```bash
agentx new --yes -n auditor --agent-mode deep --deep-reflection \
  --prompt "You audit codebases for security issues."
```
