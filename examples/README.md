# AgentX-Kit demos

Runnable demos to confirm your setup. Demos 1–3 and 5 need **no API keys**
(scaffolding, insights, the built-in MCP tools, and the flow visualizer are
offline/keyless; LLM calls are optional). Demo 4 (deep agent) makes real
model calls and needs a provider key (or a local Ollama model).

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

## 4. Deep agent (planning · filesystem · sub-agents · reflection)
Runs a `DeepAgent` with a `write_todos` planning tool, sandboxed filesystem
tools, a delegated research sub-agent, and an optional critic/reflection loop
— **needs a real LLM**, unlike the demos above.

```bash
export OPENAI_API_KEY=sk-...          # or use --provider ollama --model llama3.2 (no key)
python examples/deep_agent_demo.py --reflection
```

Or from the CLI directly: `agentx agent deep "..." --reflection`. Or generate
a project with a deep agent baked in: `agentx new --yes --agent-mode deep`.

## 5. Flow — see your code as a DAG
Renders this file's own function-call graph two ways: a static AST call graph
(no execution) and the real runtime call graph (via `@trace`).

```bash
python examples/flow_demo.py
agentx flow examples/flow_demo.py --entry preprocess     # static, via the CLI
agentx flow examples/flow_demo.py --entry preprocess -f mermaid
```
