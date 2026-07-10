# `agentx mcp`

Run AgentX-Kit as an **MCP server** — a connector for Claude / Copilot / Codex.

```bash
pip install "agentx-kit[connector]"
agentx mcp --print-config        # prints the client config
```

Once connected, a single prompt with a problem statement generates a complete project.

## Options

| Flag | Description |
|---|---|
| `--print-config` | Print MCP client config for Claude/Codex/Copilot and exit |

## Examples

```bash
agentx mcp                       # run the server (stdio) — normally launched by the MCP client
agentx mcp --print-config        # see the JSON config to paste into your client
```

Add it to a client (then restart it):

```jsonc
// Claude Desktop / Codex / Copilot — under "mcpServers"
{ "mcpServers": { "agentx-kit": { "command": "agentx", "args": ["mcp"] } } }
```

```bash
# Claude Code one-liner
claude mcp add agentx-kit -- agentx mcp
```

Then just ask, in plain language:

> "Build a customer-support agent that answers from our product docs and serves a REST API."

See [MCP connector](../features/mcp-connector.md) for the tools it exposes
(`recommend_project`, `create_agent_project`, `list_providers`, `analyze_prompt`,
`optimize_prompt`) and [MCP tool templates](../features/mcp-tools.md) for the ready-made tool
implementations (`web_search`, `text_to_speech`, `knowledge_search`, `run_sql`) you can import
directly into your own MCP server.
