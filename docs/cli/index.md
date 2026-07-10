# CLI Reference

```
agentx --help
```

```text
Usage: agentx [OPTIONS] COMMAND [ARGS]...

AgentX — provider-agnostic agentic framework + project scaffolder.

Commands:
  version    Print the installed version.
  providers  List supported LLM providers and the env vars each needs.
  dashboard  Launch the prompt observability & optimization dashboard (Streamlit).
  mcp        Run AgentX-Kit as an MCP server (connector for Claude / Copilot / Codex).
  graph      Show the structure and agent flow of a generated project.
  validate   Validate a generated project's agentx.json for structural correctness.
  upgrade    Re-run the current agentx-kit's templates over an existing project.
  flow       Show a Python file's — or a whole project's — function-call flow as a DAG.
  new        Scaffold a new agentic project (interactive by default).
  cache      Inspect/clear the local LLM response cache.
  prompt     Manage agent prompts in a generated project (edits prompts.json).
  rag        Manage the RAG knowledge base (upload docs, rebuild index).
  agent      Run autonomous and research agents.
```

Every command and command group has its own `--help`. This section documents each one with the
full flag reference and example usage:

| Command | Purpose |
|---|---|
| [`agentx new`](new.md) | Scaffold a new agentic project |
| [`agentx graph`](graph.md) | Visualize a generated project's structure |
| [`agentx validate`](validate.md) | Structural sanity-check on `agentx.json` |
| [`agentx upgrade`](upgrade.md) | Re-apply the latest templates to an existing project |
| [`agentx flow`](flow.md) | Function-call DAG for a file or whole project |
| [`agentx rag`](rag.md) | Manage a project's RAG knowledge base |
| [`agentx agent`](agent.md) | Run autonomous / research / deep agents standalone |
| [`agentx prompt`](prompt.md) | Manage an existing project's prompts |
| [`agentx dashboard`](dashboard.md) | Prompt observability & optimization UI |
| [`agentx cache`](cache.md) | Inspect/clear the local LLM response cache |
| [`agentx mcp`](mcp.md) | Run AgentX-Kit as an MCP server |
| [`agentx providers` / `agentx version`](misc.md) | List providers / print version |
