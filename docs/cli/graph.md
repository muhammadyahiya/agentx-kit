# `agentx graph`

Show the structure and agent flow of a **generated project** — agents, orchestration, tools,
RAG/memory, and the node/edge flow. Reads `agentx.json`; works with zero project dependencies
installed.

```bash
agentx graph
```

## Options

| Flag | Description |
|---|---|
| `-p, --project PATH` | Project dir (auto-detects `agentx.json`) |
| `-f, --format TEXT` | `ascii` \| `mermaid` \| `json` (default `ascii`) |
| `--introspect` | Import the compiled LangGraph for a ground-truth mermaid diagram (needs deps) |

## Examples

```bash
agentx graph                            # pretty tree of the project in cwd
agentx graph -f mermaid                 # mermaid graph (paste into a .md / VS Code)
agentx graph -f json                    # machine-readable structure
agentx graph --introspect -f mermaid    # real compiled-graph diagram
agentx graph -p ./my-bot                # target a specific project directory
```

`--introspect` actually imports the generated project's compiled LangGraph and asks it for its
own mermaid representation — the ground truth, as opposed to the static-analysis rendering used
otherwise (which works even without the project's dependencies installed).
