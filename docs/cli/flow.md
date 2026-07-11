# `agentx flow`

Show a Python file's — or a whole project's — function-call flow as a **DAG**.

```bash
agentx flow [PATH]
```

Static mode (default) parses the file (or every file under a directory) with `ast` — nothing is
imported or executed. Live mode (`--live`, single file only) actually runs the file, so any
`@agentx.flow.trace`-decorated functions are recorded with real call counts and timing. `--ui`
renders an interactive 2D/3D graph viewer instead of text; `--typecheck` attaches ruff + ty
diagnostics to it; `--serve` (single file only) starts a local server so you can click **Run** in
the viewer and watch it execute live — and now **edit source directly from the side panel**.

## Options

| Flag | Description |
|---|---|
| `PATH` | Python file or directory to analyze (default: current directory) |
| `-e, --entry TEXT` | Static mode: only the subgraph reachable from this function |
| `-f, --format TEXT` | `ascii` \| `mermaid` \| `json` \| `dot` (default `ascii`) |
| `--external / --no-external` | Include calls to non-local functions (stdlib/3rd-party) (default: include) |
| `--max-files INTEGER` | Whole-project mode only: abort instead of scanning more than this many `.py` files (default `20000`) |
| `--live` | Execute the file and render the actual runtime call graph (needs `@trace`; single file only) |
| `--ui` | Open an interactive 2D/3D DAG viewer in your browser instead of printing text |
| `-o, --out PATH` | With `--ui`, write the viewer HTML here instead of a temp file |
| `--no-open` | With `--ui`, write the viewer file but don't launch a browser |
| `--cdn` | With `--ui`, reference the 2D/3D graph libraries via CDN instead of inlining ~2MB of JS |
| `--typecheck` | Run ruff (lint) + ty (type check) and attach diagnostics to nodes (needs `agentx-kit[typecheck]`) |
| `--serve` | Start a local live-execution server: click Run in the viewer to execute and stream logs (implies `--ui`; single file only; needs `agentx-kit[server]`) |
| `--react` | With `--ui`, use the experimental React Flow v12 viewer (custom node components, ELK layout, built-in minimap) instead of the default Cytoscape viewer |

## Text renderers

```bash
agentx flow app.py                        # static call graph — no execution, works on any file
agentx flow app.py --entry train_model    # only the subgraph reachable from one function
agentx flow app.py -f mermaid             # paste into a .md file / VS Code / GitHub
agentx flow app.py -f dot > flow.dot && dot -Tsvg flow.dot -o flow.svg
agentx flow                               # whole project (cwd): modules, classes, functions
```

## Real execution graph (`--live`)

Decorate functions with `@trace` and run your code normally, or let the CLI run it for you:

```python
from agentx.flow import trace

@trace
def clean_data(): ...

@trace
def train(): ...

train()   # each call is recorded — see agentx.flow.get_current_flow()
```

```bash
agentx flow app.py --live   # runs app.py, then renders the REAL execution graph
```

## Interactive 2D/3D viewer (`--ui`)

Opens a self-contained, interactive DAG viewer in your browser — no server, no CDN, works fully
offline from one HTML file:

```bash
agentx flow --ui                        # whole project, opens the interactive viewer
agentx flow app.py --ui                 # one file
agentx flow --ui --no-open -o flow.html # write it without launching a browser
```

Nodes are colored by kind (function / class / module / external); a Modules → Classes → Full
detail control collapses large projects down to a coarse module-to-module graph by default; click
a node for its full source and file:line, click two nodes to highlight the call path between
them, and toggle a secondary experimental 3D view. A corner minimap keeps you oriented on large
graphs, and **⌘K / Ctrl+K** opens a fuzzy jump-to-node palette (e.g. type `cldt` to jump to
`clean_data`) alongside the plain search box. Layout defaults to ELK's layered algorithm (fewer
edge crossings); toggle back to dagre from the header if you prefer it. Dark/light follows your
system theme with a manual override.

### Experimental React Flow v12 viewer (`--react`)

```bash
agentx flow --ui --react   # same data, a React Flow v12 frontend instead of Cytoscape
```

A from-scratch rewrite of the viewer on [React Flow v12](https://reactflow.dev/) with custom
per-kind node components (call/error badges), ELK layered layout, compound/group nodes for the
module → class → function hierarchy with per-group collapse, and a built-in minimap + controls.
Same `nodes`/`edges` payload and `--serve` API contract as the default viewer — see
`src/agentx/flow/viewer-react/README.md` for build/rebuild instructions and current feature
status. Edit-in-place and the Run/Stop live-execution panel are implemented against the real
contract but less battle-tested than the default viewer's; treat `--react --serve` as more
experimental than `--react` alone.

## Type-checking, schemas & live execution (opt-in)

Every node's side panel always shows its declared type-hinted signature and full source, plus a
fields table for classes that look like Pydantic `BaseModel`s — all pure `ast`, no execution.

```bash
agentx flow --ui --typecheck        # attach ruff + ty diagnostics to nodes (red badge + list)
agentx flow app.py --serve          # click Run in the browser, watch it execute live
```

- **`--typecheck`** runs [ruff](https://docs.astral.sh/ruff/) and
  [ty](https://github.com/astral-sh/ty) as subprocesses and maps their diagnostics onto the
  nearest node. Requires `pip install "agentx-kit[typecheck]"`.
- **`--serve`** (single file only) starts a small local server bound to `127.0.0.1` only, with a
  random per-session token embedded in the page. Requires `pip install "agentx-kit[server]"`.

### Edit-in-place

When running with `--serve`, the side panel's source view gets an **✎ Edit** button. Clicking it
swaps the read-only view for a live [Monaco](https://microsoft.github.io/monaco-editor/) editor;
**Save** writes the change straight back to the source file on disk — overwriting exactly that
function/class's lines, nothing else in the file is touched. The node gets an "edited" badge
afterwards, since the in-memory graph snapshot is stale until you reload the page.

```bash
agentx flow app.py --serve   # then: click a node → Edit → change the code → Save
```

!!! warning
    `--serve`'s Run button and edit-in-place **execute/modify real code on your machine**. Only
    point it at code you trust. The server binds to `127.0.0.1` and every action requires the
    per-session token, but there is no sandboxing beyond that.

### The terminal box

A command box in the log pane doubles as a minimal terminal — type any command (e.g.
`streamlit run app.py`) and it runs through your OS's own shell, exactly like typing it in a real
terminal (quoting, `&&`, pipes all work). The one exception: `python <file>.py` where that file is
part of a package is routed through the same package-aware path the Run button uses, so relative
imports resolve and it gains trace events too.

## Other flags

- **`--cdn`** references the 2D/3D graph libraries via CDN instead of inlining them (~2MB smaller
  file) — off by default, since the point of `--ui` is a single file that works offline.
- **`--max-files`** (default `20000`) guards against accidentally pointing at a huge/unrelated
  directory.

## Library API

```python
from agentx.flow import build_static_flow, build_project_flow, trace, get_current_flow
from agentx.flow import render_ascii, render_mermaid, render_json, render_dot
from agentx.flow import register_renderer, get_renderer, available_renderers
from agentx.flow.htmlgen import render_html
```

| Building block | What it does |
|---|---|
| `build_static_flow(path, entry=None)` | Parse one file with `ast`, build a function-call graph |
| `build_project_flow(root, entry=None)` | Parse every file under a directory, resolving cross-file calls |
| `trace` / `get_current_flow()` | Decorate functions to record real call order, counts, timing |
| `render_ascii` / `render_mermaid` / `render_json` / `render_dot` | One shape, four text export formats |
| `register_renderer` / `get_renderer` / `available_renderers` | Renderer plugin registry |
| `render_html` | The interactive 2D/3D viewer (`--ui`), with optional `diagnostics`/`serve`/`cdn` params |
| `agentx.flow.typecheck.run_typecheck` | ruff + ty wrapper behind `--typecheck` |
| `agentx.flow.server.build_app` | The local FastAPI app behind `--serve` (including `/api/save`) |

Try it: `python examples/flow_demo.py`.
