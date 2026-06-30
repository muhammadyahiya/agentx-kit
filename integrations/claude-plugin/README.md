# AgentX-Kit — Claude Code plugin

Bundles AgentX-Kit's MCP server + a `/agentx-kit:new-agent` slash command so you
can scaffold a complete agent project from a single problem statement inside
Claude Code.

## Prerequisite
```bash
pip install "agentx-kit[connector]"   # provides `agentx mcp`
```

## Install (from this repo's marketplace)
```text
/plugin marketplace add muhammadyahiya/agentx-kit
/plugin install agentx-kit@agentx-kit
```
Then use it:
```text
/agentx-kit:new-agent a customer-support agent that answers from our docs and serves an API
```

## Or just add the MCP server (no plugin)
```bash
claude mcp add agentx-kit -- agentx mcp
```

The plugin ships:
- `.mcp.json` — registers the `agentx-kit` MCP server (`agentx mcp`).
- `commands/new-agent.md` — the `/agentx-kit:new-agent` workflow.
