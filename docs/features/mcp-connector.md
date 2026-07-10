# Use as a connector (Claude / Copilot / Codex)

AgentX-Kit ships an **MCP server**, so any MCP-capable assistant can scaffold a complete project
from **a single prompt with your problem statement**.

```bash
pip install "agentx-kit[connector]"
agentx mcp --print-config        # prints the client config below
```

Add it to your client (then restart it):

```jsonc
// Claude Desktop / Codex / Copilot — under "mcpServers"
{ "mcpServers": { "agentx-kit": { "command": "agentx", "args": ["mcp"] } } }
```

```bash
# Claude Code one-liner
claude mcp add agentx-kit -- agentx mcp
```

Now just ask, in plain language:

> "Build a customer-support agent that answers from our product docs and serves a REST API."

The assistant calls AgentX-Kit's tools and you get a complete, runnable project:

- **`recommend_project(problem_statement)`** — suggests framework, provider, agent count, and
  features.
- **`create_agent_project(problem_statement, …)`** — generates the project (infers RAG/serve/
  memory/etc. from the statement, or take explicit overrides / `enterprise=true`) and returns the
  file tree + key file contents + run steps.
- **`list_providers`**, **`analyze_prompt`**, **`optimize_prompt`** — provider list + prompt
  insights.

So from one sentence the assistant produces a pre-wired project (prompts already seeded from your
use case), ready to `uv sync && uv run`.

See [`agentx mcp`](../cli/mcp.md) for the CLI flags and
[Editor & assistant integrations](editor-integrations.md) for the VS Code extension and Claude
Code plugin that wrap this connector.
