# agentx-kit v0.18.0 — Release Notes

**Git tag:** `v0.18.0`

---

## What's new

A QA-driven bug-fix + hardening release. Three specialized review passes
(senior QA testing every CLI surface end-to-end, an architecture audit, and a
line-by-line backend code review) turned up a prioritized backlog; this
release ships the correctness bugs, concurrency/leak fixes, and the two
sprints that were judged highest-impact-per-effort. No breaking changes to
`agentx new`/`agentx graph`/static `agentx flow`.

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

## Files changed

**New files:**

- `tests/test_flow_model.py` — adjacency/dedup correctness for the new O(1)
  `Flow.add_edge`/`successors`/`predecessors`

**Modified (non-exhaustive):**

- `src/agentx/flow/typecheck.py` — rewritten around `ruff`/`ty` subprocesses
- `src/agentx/flow/_serve_runner.py`, `execrun.py`, `static.py`, `project.py`,
  `model.py`, `tracer.py`, `server.py`, `htmlgen.py` — see fixes above
- `src/agentx/scaffold/generator.py`, `src/agentx/scaffold/graphviz.py` —
  manifest versioning + overwrite error message
- `src/agentx/scaffold/templates/pyproject.toml.j2`, `pyproject.toml` —
  Python 3.14 cap, `crewai` in `[all]`, `typecheck` extra swap
- `src/agentx/cli.py` — `--typecheck` messages/guard-import updated,
  `graph`'s manifest-version error caught, top-level aliases removed
- `tests/test_flow_typecheck.py`, `test_flow_cli.py`, `test_flow_static.py`,
  `test_flow_project.py`, `test_flow_tracer.py`, `test_flow_execrun.py`,
  `test_flow_server.py`, `test_scaffold.py`, `test_sprint3.py` — extended
  for every fix above
- `README.md` — ruff/ty replaces mypy throughout, alias removal reflected

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
print(agentx.__version__)   # 0.18.0
```
