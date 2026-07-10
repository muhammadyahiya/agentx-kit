# `agentx dashboard`

Launch the prompt observability & optimization dashboard (Streamlit).

```bash
pip install "agentx-kit[dashboard]"
agentx dashboard
```

A workbench to edit a prompt and see token usage, context-window utilization, cost, quality
suggestions, one-click LLM optimization, and test runs — live.

## Options

| Flag | Description |
|---|---|
| `--port INTEGER` | Port for the dashboard server (default `8501`) |
| `--provider TEXT` | Default provider to preselect |
| `--model TEXT` | Default model to preselect |
| `--project PATH` | Project dir (default: cwd; auto-detects `prompts.json`) |

## Examples

```bash
agentx dashboard                                   # opens http://localhost:8501
agentx dashboard --port 8600
agentx dashboard --project ./my-bot --provider anthropic
agentx prompt set assistant -d                      # edit a prompt AND open the dashboard
```

Run it inside a generated AgentX project and it reads/writes that project's `prompts.json`; run
it anywhere else for a free-form prompt scratchpad.

See [Prompt dashboard](../features/dashboard.md) for what the UI shows.
