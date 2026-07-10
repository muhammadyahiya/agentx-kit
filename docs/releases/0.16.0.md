# agentx-kit v0.16.0 — Release Notes

**Released:** 2026-07-10
**PyPI:** https://pypi.org/project/agentx-kit/0.16.0/
**Git tag:** `v0.16.0`

---

## What's new

### Live execution, streamed straight into the viewer (`--serve`)

`agentx flow app.py --serve` starts a small local server (FastAPI + SSE)
that serves the same interactive viewer, plus a **Run** button. Click it and
the target file executes as a subprocess — stdout/stderr and structured
per-function call/return events stream into a log pane in real time, with
the corresponding node pulsing gold while it runs and turning green when it
returns. **Stop** terminates the running process.

```bash
agentx flow app.py --serve            # click Run, watch it execute live
agentx flow app.py --serve --no-open  # print the URL instead of opening a browser
```

Safety: binds to `127.0.0.1` only, and every action endpoint (`run`/`stop`/
`stream`) requires a random per-session token embedded in the page — but
clicking Run **does execute real code on your machine**, so only point it at
code you trust. This is a distinct, opt-in mode from `--live` (which stays
the fast, synchronous, text-output runtime trace); the two can't be combined.
Requires `pip install "agentx-kit[server]"` (reuses the existing `server`
extra — no new required dependency for the default `--ui`).

Mechanically: `agentx/flow/tracer.py` gained an optional event hook so
`@trace`'s existing call/return bookkeeping can also emit structured events;
a new subprocess entry point (`agentx/flow/_serve_runner.py`) sets that hook
and prints sentinel-prefixed JSON lines, which the server
(`agentx/flow/server.py`) tells apart from the target script's own stdout
and forwards over SSE.

### Type-checking, Pydantic schemas & full source (always-on + `--typecheck`)

Every node's side panel now always shows its declared, type-hinted
signature and the *whole* function/class body (not a fixed-size snippet),
plus a fields table (name/type/default/required) for classes that look like
Pydantic `BaseModel`s — all pure `ast`, no execution, no new dependency.

```bash
agentx flow --ui --typecheck   # attach mypy diagnostics to nodes
```

`--typecheck` runs [mypy](https://mypy.readthedocs.io/) in-process (no
Node/toolchain requirement) and maps its `file:line` diagnostics onto the
nearest node — an inline red border marks nodes with errors, and the side
panel lists them. Requires `pip install "agentx-kit[typecheck]"` (new
`typecheck` extra, `mypy>=1.8.0`).

Existing single-file static/live/ascii/mermaid/json/dot behavior, and the
default static `--ui` (no new flags), are unchanged — this release is
entirely additive.

---

## Files changed

**New files:**

- `src/agentx/flow/typecheck.py` — mypy wrapper (`run_mypy`) + node-diagnostic mapping
- `src/agentx/flow/schema.py` — AST-only Pydantic field extraction
- `src/agentx/flow/server.py` — the `--serve` FastAPI app (run/stop/stream, token-gated)
- `src/agentx/flow/_serve_runner.py` — subprocess entry point for `--serve`'s Run button
- `tests/test_flow_typecheck.py` (4 tests), `tests/test_flow_schema.py` (5 tests),
  `tests/test_flow_server.py` (5 tests)

**Modified files:**

- `src/agentx/flow/tracer.py` — optional event hook (`set_event_hook`), backward compatible
- `src/agentx/flow/htmlgen.py` — signature/full-source/schema/diagnostics in the payload,
  `render_html` gains `diagnostics`/`serve`/`serve_token` kwargs, Run/Stop + log pane +
  SSE client JS
- `src/agentx/cli.py` — `--typecheck`/`--serve` flags, guard-imports, flag-combo validation
- `pyproject.toml` — new `typecheck` extra (`mypy>=1.8.0`), added to `all`
- `tests/test_flow_html.py` (+9 tests), `tests/test_flow_cli.py` (+6 tests)
- `README.md` — "Type-checking, schemas & live execution" section

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
pip install "agentx-kit[typecheck]"   # for --typecheck
pip install "agentx-kit[server]"      # for --serve
```

Verify:

```python
import agentx
print(agentx.__version__)   # 0.16.0
```
