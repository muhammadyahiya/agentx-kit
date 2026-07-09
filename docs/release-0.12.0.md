# agentx-kit v0.12.0 — Release Notes

**Released:** 2026-07-08  
**PyPI:** https://pypi.org/project/agentx-kit/0.12.0/  
**Git tag:** `v0.12.0` (commit `24df41d`)  
**GitHub Actions run:** [28916803934](https://github.com/muhammadyahiya/agentx-kit/actions/runs/28916803934) — **success**

---

## What's new

### MCP tool templates

Four production-ready FastMCP tool templates are now bundled in `agentx.tools.mcp_server`. Users can spin up an MCP server exposing any combination of these tools with a single function call — no boilerplate required.

| Tool group | MCP tool names | Install extra |
|---|---|---|
| Web search | `web_search`, `fetch_url` | `agentx-kit[connector]` |
| Text-to-speech | `text_to_speech` | `agentx-kit[voice]` |
| Knowledge research | `knowledge_search` | `agentx-kit[connector]` |
| Database (read-only SQL) | `run_sql`, `list_tables` | `agentx-kit[connector]` |

**Quick start:**

```python
from agentx.tools.mcp_server import build_mcp_server, run_mcp_server

mcp = build_mcp_server(
    name="my-tools",
    tools=["web_search", "knowledge_research", "database"],
    knowledge_root="./knowledge",
    db_path="./data.db",
)
mcp.run()   # stdio transport — wire into Claude, Copilot, Codex, etc.
```

### Project scaffolder integration

`agentx new` now offers an MCP step in the interactive wizard. Selecting MCP generates three files inside the project package:

```
src/<pkg>/mcp/
    __init__.py
    server.py          # FastMCP server wired to selected tools
    client_demo.py     # async client that exercises every tool
```

`pyproject.toml` gains a `<slug>-mcp-server` entry-point so the server can be launched with:

```bash
uv run <slug>-mcp-server
# or add it to Claude:
claude mcp add <slug>-tools -- uv run <slug>-mcp-server
```

`mcp_servers.json` in the generated project is updated automatically.

### Connector (`agentx mcp`) integration

The `build_project_from_statement` API and the `create_agent_project` MCP tool both accept a `mcp_tools` list. The connector's `recommend_spec` heuristic also infers tool subsets from problem-statement keywords:

```python
from agentx.connector import build_project_from_statement, recommend_spec

rec = recommend_spec("Connect to our SQL database and speak the answer aloud.")
# → rec["mcp_tools"] == ["database", "tts"]

out = build_project_from_statement(
    "Chat assistant with web search",
    features=["mcp"], mcp_tools=["web_search"],
    output_dir="./my-project", create_venv=False,
)
```

### New demo scripts

| Script | What it does |
|---|---|
| `examples/mcp_toolkit_server.py` | Standalone FastMCP server with all four tools |
| `examples/mcp_toolkit_client.py` | Async MCP client — handshake, list tools, call each one |

Run with:

```bash
pip install "agentx-kit[connector,voice]"
python examples/mcp_toolkit_client.py
```

---

## Files changed

**New files:**

- `src/agentx/tools/mcp_server.py` — core library (`build_mcp_server`, `run_mcp_server`, `register_*` helpers, `AVAILABLE_MCP_TOOLS`)
- `src/agentx/scaffold/templates/pkg/mcp/__init__.py.j2`
- `src/agentx/scaffold/templates/pkg/mcp/server.py.j2`
- `src/agentx/scaffold/templates/pkg/mcp/client_demo.py.j2`
- `examples/mcp_toolkit_server.py`
- `examples/mcp_toolkit_client.py`
- `tests/test_mcp_server_tools.py` (6 tests)

**Modified files:**

- `src/agentx/tools/__init__.py` — re-exports `build_mcp_server`, `run_mcp_server`, `AVAILABLE_MCP_TOOLS`
- `src/agentx/scaffold/spec.py` — `mcp_tools: list[str]` field + `effective_mcp_tools` computed property
- `src/agentx/scaffold/generator.py` — generates `mcp/` package; adds `voice` extra when TTS selected
- `src/agentx/scaffold/wizard.py` — MCP tool checkbox sub-prompt
- `src/agentx/scaffold/templates/pyproject.toml.j2` — MCP server entry-point
- `src/agentx/scaffold/templates/mcp_servers.json.j2` — `<slug>-tools` server entry
- `src/agentx/scaffold/templates/README.md.j2` — "Your own MCP server" section
- `src/agentx/cli.py` — `--mcp-tools` CLI option
- `src/agentx/connector/recommend.py` — `_infer_mcp_tools()` keyword heuristic
- `src/agentx/connector/build.py` — `mcp_tools` parameter threading
- `src/agentx/connector/server.py` — `mcp_tools` in `create_agent_project` MCP tool
- `tests/test_scaffold.py` — 4 new test cases
- `tests/test_connector.py` — 3 new test cases
- `README.md`, `DESIGN.md`, `examples/README.md` — documentation updates

---

## Publish pipeline

### Trigger mechanism

The publish workflow (`.github/workflows/publish.yml`) fires on any `v*` tag push or manual `workflow_dispatch`. It uses **OIDC Trusted Publishing** — no PyPI API token is stored in GitHub secrets.

### Pipeline steps

```
push tag v0.12.0
    │
    ▼
┌─────────────────────────────┐
│  Job: Build distributions   │  ~9s
│  - actions/checkout@v4      │
│  - astral-sh/setup-uv@v5    │
│  - uv build (sdist + wheel) │
│  - uvx twine check dist/*   │
│  - upload artifact: dist/   │
└─────────────┬───────────────┘
              │ artifact: dist/
              ▼
┌─────────────────────────────────────────┐
│  Job: Publish to PyPI                   │  ~21s
│  environment: pypi (OIDC)               │
│  permissions: id-token: write           │
│  - download artifact: dist/             │
│  - pypa/gh-action-pypi-publish@release  │
│    → uploads wheel + sdist to PyPI      │
│    → generates digital attestation      │
└─────────────────────────────────────────┘
```

### What went wrong on the first attempt (and how it was fixed)

The first `v0.12.0` tag was pushed before `pyproject.toml` was updated. The build job checked out code where `pyproject.toml` still read `version = "0.11.2"`, so it produced `agentx_kit-0.11.2-py3-none-any.whl`. PyPI rejected the upload with `400 File already exists`.

**Fix:** bumped `pyproject.toml` to `0.12.0`, committed, pushed `main`, then force-moved the tag:

```bash
git tag -f v0.12.0          # move tag to new commit
git push origin v0.12.0 --force
```

The second run (ID 28916803934) succeeded.

### Artifacts published

| File | Size |
|---|---|
| `agentx_kit-0.12.0-py3-none-any.whl` | ~178 KB |
| `agentx_kit-0.12.0.tar.gz` | ~175 KB |

---

## Installation

```bash
# Minimal (no MCP tools)
pip install agentx-kit

# With MCP tools + voice
pip install "agentx-kit[connector,voice]"

# Everything
pip install "agentx-kit[all]"
```

## Upgrade

```bash
pip install --upgrade agentx-kit
```

Verify:

```python
import agentx
print(agentx.__version__)   # 0.12.0
```
