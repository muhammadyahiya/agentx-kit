# Editor & assistant integrations

The same MCP connector powers ready-made integrations (see
[`integrations/`](https://github.com/muhammadyahiya/agentx-kit/tree/main/integrations)):

- **VS Code extension** ([`integrations/vscode`](https://github.com/muhammadyahiya/agentx-kit/tree/main/integrations/vscode)) —
  commands for *New Agent Project*, *Open Prompt Dashboard*, *Add Prompt*, *Cache Stats*, and
  *Register MCP Server for Copilot* (writes `.vscode/mcp.json`). Build with `vsce package`.
- **GitHub Copilot** (agent mode) — add the MCP server via `.vscode/mcp.json`:

  ```jsonc
  { "servers": { "agentx-kit": { "command": "agentx", "args": ["mcp"] } } }
  ```

  (the VS Code command above writes this for you), then ask Copilot to build an agent.
- **Claude Code plugin** ([`integrations/claude-plugin`](https://github.com/muhammadyahiya/agentx-kit/tree/main/integrations/claude-plugin)):

  ```text
  /plugin marketplace add muhammadyahiya/agentx-kit
  /plugin install agentx-kit@agentx-kit
  /agentx-kit:new-agent a support agent that answers from our docs and serves an API
  ```

- **Claude Desktop / Codex** — add the connector config from `agentx mcp --print-config`.

See [MCP connector](mcp-connector.md) for what happens once connected.
