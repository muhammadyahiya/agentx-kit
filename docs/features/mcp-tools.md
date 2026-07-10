# MCP tool templates (web search · TTS · knowledge research · database)

AgentX-Kit ships ready-made **MCP server tools**, importable directly — no generated project
required:

```bash
pip install "agentx-kit[connector,voice]"
```

```python
from agentx.tools.mcp_server import build_mcp_server

mcp = build_mcp_server(
    name="my-tools",
    tools=["web_search", "tts", "knowledge_research", "database"],  # pick any subset
    knowledge_root="./knowledge",   # scanned by knowledge_research (md/txt/pdf/docx/csv/xlsx)
    db_path="./data.db",            # queried (read-only) by database
)
mcp.run()   # stdio MCP server — connect from Claude, a LangChain agent, or your own client
```

| Tool | What it does | Backing |
|---|---|---|
| `web_search` | DuckDuckGo search | `agentx.tools.builtin` |
| `fetch_url` | Safe HTTP(S) GET + HTML strip | `agentx.tools.builtin` |
| `text_to_speech` | Synthesize speech, returns an audio file path | `agentx.voice.tts` (edge-tts/OpenAI/pyttsx3) |
| `knowledge_search` | Keyword search over local documents — no embeddings needed | `agentx.rag.loaders` |
| `run_sql` / `list_tables` | Read-only SQLite queries (rejects non-`SELECT`) | `sqlite3` |

Try it:

```bash
python examples/mcp_toolkit_server.py
python examples/mcp_toolkit_client.py
```

## Or generate a project with these baked in

Pick "Integrate MCP tools?" in the wizard (or `agentx new --yes --mcp --mcp-tools
web_search,database`) and the project gets its own `src/<pkg>/mcp/server.py` + a
`mcp/client_demo.py` sample script, already registered in `mcp_servers.json` so the agent(s) can
call these tools too:

```bash
uv run my-bot-mcp-server                        # run your generated MCP server
uv run python -m my_bot.mcp.client_demo          # sample client
```
