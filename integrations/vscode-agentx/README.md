# AgentX for VS Code

A thin wrapper over the [`agentx`](https://pypi.org/project/agentx-kit/) CLI. It
does not bundle Python — it shells out to the `agentx` executable it finds in
your workspace's `.venv` (or on `PATH`).

## Commands (Command Palette → "AgentX:")

| Command | What it does |
|---|---|
| **AgentX: New Project…** | Guided pick-list wizard → `agentx new --yes …` in a terminal |
| **AgentX: Show Graph** | `agentx graph --format mermaid` → rendered in a webview (mermaid.js) |
| **AgentX: Launch Dashboard** | `agentx dashboard` (opens http://localhost:8501) |
| **AgentX: Run Project** | `uv run <slug>` (slug read from `agentx.json`) |
| **AgentX: List Providers** | `agentx providers` → output channel |

Right-click a folder in the Explorer → **AgentX: Show Graph** to visualize that project.

## Requirements

- The `agentx` CLI installed (`pip install agentx-kit`), typically in a project
  `.venv`. Override the location with the **`agentx.cliPath`** setting.

## Install (development)

```bash
cd integrations/vscode-agentx
# Press F5 in VS Code to launch an Extension Development Host,
# or package with: npx @vscode/vsce package
```

No build step — the extension is plain CommonJS (`extension.js`).
