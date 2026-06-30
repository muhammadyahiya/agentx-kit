# AgentX-Kit — VS Code extension

Scaffold agent projects, open the prompt dashboard, and wire AgentX-Kit into
**GitHub Copilot** (agent mode) — without leaving VS Code.

## Prerequisite
```bash
pip install "agentx-kit[all]"   # provides the `agentx` CLI the extension calls
```

## Commands (⇧⌘P)
- **AgentX: New Agent Project** — name + use case → `agentx new`
- **AgentX: Open Prompt Dashboard** — `agentx dashboard`
- **AgentX: Add Agent Prompt** — `agentx prompt set … -d`
- **AgentX: Show Response-Cache Stats** — `agentx cache stats`
- **AgentX: Register MCP Server for Copilot** — writes `.vscode/mcp.json` so Copilot
  agent mode can call AgentX-Kit's tools (e.g. *"build a support agent over our docs"*).

Set a custom CLI path with the `agentx.command` setting.

## Build / install locally
```bash
npm install -g @vscode/vsce
cd integrations/vscode
vsce package           # -> agentx-kit-0.1.0.vsix
code --install-extension agentx-kit-0.1.0.vsix
```

## Publish (needs a Marketplace publisher + PAT)
```bash
vsce login <publisher>
vsce publish
```
See https://code.visualstudio.com/api/working-with-extensions/publishing-extension.
