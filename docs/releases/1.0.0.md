# agentx-kit v1.0.0 — Release Notes

**Git tag:** `v1.0.0`

---

## What's new

A QA-driven bug-fix, architecture-cleanup, and feature release. Three
specialized review passes (senior QA testing every CLI surface end-to-end, an
architecture audit, and a line-by-line backend code review) turned up a
prioritized backlog; this release ships every item from it — the correctness/
performance/concurrency fixes, the architecture cleanups, and the full
roadmap feature set. `0.18.0`/`0.19.0` were never published as standalone
releases — everything below landed in one continuous branch and ships
together as `v1.0.0`. No breaking changes to `agentx new`/`agentx graph`/
static `agentx flow`'s existing behavior (see "Breaking changes" below for
the few narrow exceptions).

### `agentx flow --typecheck` now runs ruff + ty instead of mypy

mypy is dropped in favor of [ruff](https://docs.astral.sh/ruff/) (lint) and
[ty](https://github.com/astral-sh/ty) (Astral's type checker) — both are
fast Rust binaries from the same team as `uv`, so `--typecheck` is
noticeably quicker. `agentx-kit[typecheck]` now installs `ruff` + `ty`
instead of `mypy`. Diagnostics now carry which tool flagged them
(`"tool": "ruff"` or `"tool": "ty"`) and both plug into the exact same
per-node badge/list UI in `--ui`.

`agentx.flow.typecheck.run_mypy` is renamed to
`agentx.flow.typecheck.run_typecheck` — this is a breaking rename for direct
importers of that (already-optional, already-experimental) function; the
CLI-facing `--typecheck` flag is unchanged.

### Correctness fixes

- **`--serve`'s "Run" no longer reports success on a failed script.** A
  target script calling `sys.exit(1)` (or any nonzero/`SystemExit`) used to
  be swallowed by `_serve_runner.py`, so the browser always saw `exit_code:
  0` regardless of whether the script actually failed.
- **Nested function calls are no longer misattributed to the outer
  function.** `def outer(): \n    def inner(): foo()` used to show `foo()`
  as a call made by both `outer` *and* `outer.inner` in the static call
  graph — the AST visitor now stops at nested `def`/`class` boundaries when
  collecting one function's call sites.
- **A syntax error in the target file no longer dumps a raw Python
  traceback.** `agentx flow broken.py` now prints `Syntax error in
  broken.py: <message> (line N)` and exits 1, matching whole-project mode's
  existing behavior.
- **A permission-denied or non-UTF-8 file no longer aborts a whole-project
  `agentx flow`.** `build_project_flow` now skips unreadable/binary `.py`
  files (same treatment as files with a syntax error) instead of raising.
- **`@trace` now works correctly on generator and async-generator
  functions.** Previously, decorating a generator function recorded ~0ms
  and a call that "returned" instantly, because calling a generator function
  only creates the generator object without running its body — the wrapper
  now spans the full iteration (first `next()` through exhaustion/close).
- **`crewai` was missing from the `agentx-kit[all]` bundle** — `pip install
  'agentx-kit[all]'` silently didn't install CrewAI, so
  `agentx new --framework crewai` scaffolded a project that couldn't import
  at runtime. Fixed, with a `<1.0.0` upper bound alongside the existing
  `[crewai]` extra to avoid an untested future major version breaking
  generated projects.
- **`requires-python` bumped to `<3.15`** (was `<3.14`, and Python 3.14 is
  already released) — in both `pyproject.toml` and every newly-scaffolded
  project's `pyproject.toml`/`agentx.json`.
- **`agentx new`'s overwrite error** no longer says the Python-only
  `overwrite=True` — it now names both the CLI flag and the API kwarg.

### Performance & resource-leak fixes

- **`Flow.add_edge`/`successors`/`predecessors`** were O(n) per call (a
  linear scan over every edge), making project-wide graph construction
  O(edges²) for large codebases. Now backed by a same-key index and
  adjacency lists — O(1) per call, including when a subgraph's `.edges` is
  reassigned directly (as `_subgraph_from` does).
- **`--ui`'s HTML generation re-read every source file from disk once per
  function/class node** (on top of the AST, which was already cached) — now
  cached alongside the AST, so a 100-function/10-file project reads each
  file once instead of ~10 times.
- **`--serve`'s `runs` dict grew forever** — every "Run" click left behind a
  `_Run` (a `Popen` + `Queue`) that was never freed. Finished runs are now
  swept out 5 minutes after completion.
- **`--serve`'s SSE stream could leak an executor thread** on browser
  disconnect — `queue.get()` was called with no timeout inside
  `run_in_executor`, so a disconnected client's read could sit blocked in
  the thread pool indefinitely for a silent/long-running subprocess. Now
  polls with a 1-second timeout so cancellation is respected promptly.
- **`asyncio.get_event_loop()`** (deprecated since Python 3.10 when called
  with no running loop) replaced with `asyncio.get_running_loop()` in the
  SSE stream handler.
- **`tracer.py`'s module-global state** (`_flow`, `_event_hook`) is now
  guarded by a lock — concurrent `@trace`-decorated calls from multiple
  threads could previously race past `add_edge`'s duplicate-check and
  create duplicate edges, or one thread's `set_event_hook` could race
  another's in-flight run.

### `agentx.json` manifest versioning

Every newly-generated project's `agentx.json` now includes
`"manifest_version": 1`. `agentx graph` (via `graphviz.load_manifest`)
checks this and raises a clear error — "generated by a newer agentx-kit ...
upgrade with pip install -U agentx-kit" — instead of silently
misinterpreting an unrecognized future manifest shape. Manifests with no
`manifest_version` key (every project generated before this release) are
treated as version 1, so nothing breaks for existing projects.

### CLI cleanup

The top-level `agentx run`/`agentx research`/`agentx deep` aliases for
`agentx agent run`/`research`/`deep` are removed — they duplicated entries
in `--help` and permanently blocked those verbs for any future unrelated
top-level command. `agentx agent run`/`research`/`deep` (unchanged) remain
the only way to invoke these.

---

## Architecture cleanup

- **`agentx flow`'s AST call-collection logic** (previously duplicated
  between `static.py` and `project.py`, one importing the other's private
  symbols) is now shared from a new `flow/_ast_helpers.py`.
- **`scaffold/graphviz.py`'s own `Flow` dataclass** — a completely different,
  incompatible shape from `agentx.flow.model.Flow` (agent-orchestration graph
  vs. AST call graph) that happened to share the same name — is renamed to
  `ManifestFlow`.
- **`schema.py`'s Pydantic-field extraction** no longer re-walks the whole
  AST tree once per class; `build_class_index(tree)` builds a
  `{lineno: ClassDef}` index once per file instead.
- **`project.py`'s whole-project builder** no longer holds every file's
  parsed AST tree in memory simultaneously across both its passes — pass 2
  now re-parses each file from disk just before processing it, trading a bit
  of CPU for peak memory that no longer scales with project size.
- **`--ui`'s ~400-line embedded JS string** is extracted from `htmlgen.py`
  into a real `flow/viewer/app.js` file (lintable, diffable, syntax-
  highlighted in an editor) — loaded like the existing vendored libraries.
- **The HTML template assembly** (an order-dependent `str.replace` chain,
  since the app-JS placeholder had to be substituted before the graph-data
  placeholder) is replaced with a real Jinja2 template
  (`flow/viewer/viewer.html.j2`) — Jinja2 was already a hard dependency.

## New features

- **`agentx validate [--project]`** checks a generated project's
  `agentx.json` for structural issues: unknown framework/provider/
  agent_mode/orchestration/memory values, unknown `mcp_tools`, extras that
  don't appear in `pyproject.toml`, agents with no `prompts.json` entry, and
  a missing `.env.example`. Exits 1 on any error-level finding.
- **`agentx upgrade [--project] [--apply] [--force]`** re-runs the
  *currently installed* agentx-kit's templates over an existing project and
  shows (dry-run by default) or applies what changed — useful after
  upgrading agentx-kit to pick up template fixes in an already-generated
  project. `prompts.json` and `knowledge/`/`data/skills/` are left alone
  unless `--force` is also passed, since those are meant to be hand/CLI-
  edited, not silently regenerated.
- **`agentx flow --ui --cdn`** references the 2D/3D graph libraries via CDN
  instead of inlining ~2MB of JS — off by default (the point of `--ui` is a
  file that still works fully offline).
- **`agentx flow --max-files`** (CLI default: 20000) guards against
  accidentally pointing whole-project mode at a huge/unrelated directory;
  `build_project_flow(..., max_files=...)` is available as a library
  parameter too (no default cap there).
- **`agentx flow --live` now exits 1** when zero `@trace` calls were
  recorded — previously exited 0, masking a misconfigured `--live` run
  (missing decorators, or a target that traces nothing) from CI/scripts.
- **A generated project now includes `tests/test_main.py`** — a smoke test
  confirming the project imports cleanly and exposes a callable `run_text`,
  no API key or network access required. `pyproject.toml` gains a
  `dev = ["pytest>=8.0.0"]` optional-dependencies group and the README gets
  a "## Test" section (`uv sync --extra dev && uv run pytest`).
- **`agentx new --list-frameworks` / `--list-providers`** print valid
  `--framework`/`--provider` choices and exit, without needing `--help`.
- **`agentx new --quiet` / `--json`** — `--quiet` suppresses the result
  panel, `--json` prints a one-line machine-readable summary instead
  (`{"ok": true, "name", "target_dir", "files", "venv_created", "synced"}`,
  or `{"ok": false, "error"}` on failure) — for CI/tooling wrappers.
- **A renderer plugin registry**: `agentx.flow.register_renderer(name, fn)` /
  `get_renderer(name)` / `available_renderers()`. `agentx flow -f <name>`
  now dispatches through this registry instead of a hardcoded
  `if/elif` chain — third-party code can add a new output format without
  patching agentx-kit. An unrecognized `-f/--format` now errors clearly
  (`Unknown format 'x'. Available: ascii, dot, json, mermaid`) instead of
  silently falling back to ascii.
- **`build_project_flow` warns on circular imports** between project modules
  (`Circular import detected: pkg.a -> pkg.b -> pkg.a`) and **on star
  imports** (`from pkg import *` — can't be resolved statically, so calls
  through the names it introduces show as external).

## Breaking changes

Narrow, all in already-optional/experimental surfaces:

- `agentx.flow.typecheck.run_mypy` → `run_typecheck` (rename; the
  `--typecheck` CLI flag itself is unchanged).
- `agentx flow -f <unrecognized-format>` now errors instead of silently
  rendering ascii.
- `agentx run`/`agentx research`/`agentx deep` (top-level aliases) removed —
  use `agentx agent run`/`research`/`deep`.
- `scaffold.graphviz.Flow` renamed to `scaffold.graphviz.ManifestFlow` (an
  internal type with no test/code outside this package referencing it by
  name).

---

## Files changed

**New files:**

- `src/agentx/flow/_ast_helpers.py` — shared `CallCollector`/`subgraph_from`
- `src/agentx/flow/viewer/app.js`, `viewer.html.j2` — externalized JS + Jinja2 template
- `src/agentx/scaffold/validate.py`, `src/agentx/scaffold/upgrade.py`
- `src/agentx/scaffold/templates/tests/test_main.py.j2`
- `tests/test_flow_model.py`, `test_scaffold_validate.py`,
  `test_scaffold_upgrade.py`, `test_cli_new.py`

**Modified (non-exhaustive):**

- `src/agentx/flow/typecheck.py` — rewritten around `ruff`/`ty` subprocesses
- `src/agentx/flow/_serve_runner.py`, `execrun.py`, `static.py`, `project.py`,
  `model.py`, `tracer.py`, `server.py`, `htmlgen.py`, `schema.py`, `render.py` —
  see fixes/features above
- `src/agentx/scaffold/generator.py`, `src/agentx/scaffold/graphviz.py` —
  manifest versioning, overwrite error message, `ManifestFlow` rename,
  `tests/` scaffold wiring
- `src/agentx/scaffold/templates/pyproject.toml.j2`, `README.md.j2`,
  `pyproject.toml` — Python 3.14 cap, `crewai` in `[all]`, `typecheck` extra
  swap, `dev` extras group, "## Test" section
- `src/agentx/cli.py` — `validate`/`upgrade` commands, `--typecheck` messages/
  guard-import updated, `graph`'s manifest-version error caught, top-level
  aliases removed, `--cdn`/`--max-files` on `flow`, renderer-registry dispatch,
  `--list-frameworks`/`--list-providers`/`--quiet`/`--json` on `new`
- `tests/test_flow_typecheck.py`, `test_flow_cli.py`, `test_flow_static.py`,
  `test_flow_project.py`, `test_flow_tracer.py`, `test_flow_execrun.py`,
  `test_flow_server.py`, `test_flow_html.py`, `test_flow_schema.py`,
  `test_flow_render.py`, `test_scaffold.py`, `test_sprint3.py` — extended
  for every fix/feature above
- `README.md` — ruff/ty replaces mypy throughout, alias removal reflected,
  new commands/flags documented

---

## Publish pipeline

Same mechanism as prior releases: `.github/workflows/publish.yml` fires on
any `v*` tag push, builds with `uv build`, checks with `twine check`, and
publishes via OIDC Trusted Publishing. Version bumped in `pyproject.toml`
and `src/agentx/__init__.py` before tagging, per the process established in
`docs/release-0.12.0.md`.

## Installation

```bash
pip install --upgrade agentx-kit
```

Verify:

```python
import agentx
print(agentx.__version__)   # 1.0.0
```
