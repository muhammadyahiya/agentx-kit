# agentx-kit v0.15.0 — Release Notes

**Released:** 2026-07-10
**PyPI:** https://pypi.org/project/agentx-kit/0.15.0/
**Git tag:** `v0.15.0`

---

## What's new

### Whole-project flow graphs

`agentx flow` no longer requires a single file. Point it at a directory (or
run it with no path at all, defaulting to the current directory) and it
walks every `.py` file, building one project-wide function-call graph with
packages, modules, classes, and functions as nodes — resolving cross-file
calls through each file's own `import`/`from ... import` statements.

```bash
agentx flow                       # whole project (cwd)
agentx flow src/my_package        # whole project (explicit path)
agentx flow app.py                # single file — unchanged, still works exactly as before
```

`build_project_flow(root, entry=None, include_external=True, include_tests=True)`
is the new library entry point, alongside the existing `build_static_flow`.

### Interactive 2D/3D DAG viewer (`--ui`)

`agentx flow --ui` renders a self-contained, interactive HTML viewer instead
of text — no server, no CDN, works fully offline from one file:

```bash
agentx flow --ui                          # whole project
agentx flow app.py --ui                   # one file
agentx flow --ui --no-open -o flow.html   # write it without launching a browser
```

- Nodes colored by kind (function / class / module / external), colorblind-safe palette
- Modules → Classes → Full detail control, collapsing large projects to a
  coarse module-to-module graph by default (aggregated edges, not just hidden nodes)
- Click a node for its source snippet and file:line; click two nodes to
  highlight the call path between them; search by name; toggle kinds via the legend
- Secondary experimental 3D view (layered by call depth via `dagMode`)
- Dark/light follows system theme, with a manual override

The viewer's JS dependencies (Cytoscape.js + dagre + cytoscape-dagre for 2D,
three.js + 3d-force-graph for 3D) are vendored under `agentx/flow/vendor/`
and inlined directly into the generated HTML — no new *required* Python
dependency, and `agentx flow` keeps working with zero project dependencies
installed.

---

## Files changed

**New files:**

- `src/agentx/flow/project.py` — `build_project_flow`, directory walker,
  import-aware cross-file call resolution
- `src/agentx/flow/htmlgen.py` — `render_html`, the self-contained viewer
- `src/agentx/flow/vendor/` — vendored 2D/3D graph JS libraries
- `tests/test_flow_project.py` (11 tests), `tests/test_flow_html.py` (9 tests)

**Modified files:**

- `src/agentx/flow/model.py` — `FlowNode` gains `kind`/`module`/`parent`,
  `Flow` gains `scope` (all backward-compatible defaults)
- `src/agentx/flow/__init__.py` — exports `build_project_flow`, `render_html`
- `src/agentx/cli.py` — `flow` command: optional directory `path` (default
  cwd), new `--ui`/`--out`/`--no-open` flags
- `tests/test_flow_cli.py` — 6 new test cases for directory mode and `--ui`
- `README.md` — "Flow" section documents whole-project mode and `--ui`

Existing single-file static/live/ascii/mermaid/json/dot behavior is
unchanged — this release is additive.

---

## Publish pipeline

Same mechanism as prior releases: `.github/workflows/publish.yml` fires on
any `v*` tag push, builds with `uv build`, checks with `twine check`, and
publishes via OIDC Trusted Publishing (no stored PyPI token). Version was
bumped in `pyproject.toml` and `src/agentx/__init__.py` **before** tagging,
per the lesson recorded in `docs/release-0.12.0.md`.

## Installation

```bash
pip install --upgrade agentx-kit
```

Verify:

```python
import agentx
print(agentx.__version__)   # 0.15.0
```
