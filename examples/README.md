# AgentX-Kit demos

Runnable demos to confirm your setup — **no API keys required** (scaffolding,
insights, and the built-in MCP tools are offline/keyless; LLM calls are optional).

## 1. Local setup test
Verifies the install, lists providers, scaffolds a demo project, and exercises
prompt insights + the response cache.

```bash
pip install "agentx-kit[all]"
bash examples/demo_local.sh
```

## 2. MCP connector test (the Claude / Copilot / Codex path)
Spawns `agentx mcp` over stdio, does a real MCP handshake, lists the tools, and
scaffolds a complete project from a one-line problem statement — exactly what an
assistant does when connected.

```bash
pip install "agentx-kit[connector]"
python examples/demo_mcp.py
```

Then wire it into Claude for real:
```bash
claude mcp add agentx-kit -- agentx mcp
```

## 3. MCP tool templates (web search, TTS, knowledge research, database)
Runs a standalone MCP server exposing the built-in tools, then a client that
connects to it, lists tools/resources/prompts, and calls each one.

```bash
pip install "agentx-kit[connector,voice]"
python examples/mcp_toolkit_client.py
```

Point it at real data by editing `examples/mcp_toolkit_server.py`'s
`knowledge_root` / `db_path`, or generate a project with these tools baked in
(`agentx new --yes --mcp`).
