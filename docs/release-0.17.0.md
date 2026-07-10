# agentx-kit v0.17.0 — Release Notes

**Released:** 2026-07-10
**PyPI:** https://pypi.org/project/agentx-kit/0.17.0/
**Git tag:** `v0.17.0`

---

## What's new

### Fix: `--live`/`--serve` failed on real packages using relative imports

Reported after 0.16.0 shipped: running `agentx flow server.py --live` (or
`--serve`) against a file that's part of a package — e.g. a generated
project's `src/<pkg>/server.py` doing `from .config import settings` —
failed with:

```
Error while running server.py: attempted relative import with no known parent package
```

Root cause: both modes executed the target via `runpy.run_path(path,
run_name="__main__")`, which runs the file as a bare script — Python never
learns it belongs to a package, so any relative import inside it fails.

Fixed with a new shared helper, `agentx/flow/execrun.py`: if the target
file's directory has an `__init__.py`, it's now run as a real module within
its package (the same thing `python -m pkg.module` does — find the package
root, put it on `sys.path`, `runpy.run_module` instead), so relative imports
resolve correctly. Standalone scripts (no `__init__.py`) are unaffected —
same behavior as before.

### `--serve`'s log pane is now also a minimal terminal

A command box in the log pane lets you type any command (not just click the
fixed "Run" button) — e.g. `python main.py`, `pytest`, `ls` — and it runs
with the same live stdout/stderr streaming. If the command matches `python
<file>.py` and that file turns out to be part of a package, it's
transparently routed through the same package-aware execution as the Run
button (gaining trace-event support too), so typing `python main.py` for a
package-relative file just works instead of hitting the same import error.

```bash
agentx flow app.py --serve
# then in the browser: type `python main.py` in the log pane's command box
```

---

## Files changed

**New files:**

- `src/agentx/flow/execrun.py` — `run_target()`, the package-aware execution helper
- `tests/test_flow_execrun.py` (4 tests)

**Modified files:**

- `src/agentx/cli.py` — `--live` now calls `execrun.run_target` instead of raw `runpy.run_path`
- `src/agentx/flow/_serve_runner.py` — same, for `--serve`'s default Run button
- `src/agentx/flow/server.py` — `/api/run` accepts an optional `{"command": "..."}` body
  for the terminal box; `python <file>.py` commands targeting a package file are
  rewritten to the package-aware execution path
- `src/agentx/flow/htmlgen.py` — command-input terminal bar in the log pane, wired to
  the new `/api/run` body param
- `tests/test_flow_server.py` (+5 tests)

No changes to the default static `--ui`, text renderers, or `--typecheck` — this
release is a bug fix plus one additive capability on top of 0.16.0's `--serve`.

---

## Publish pipeline

Same mechanism as prior releases: `.github/workflows/publish.yml` fires on
any `v*` tag push, builds with `uv build`, checks with `twine check`, and
publishes via OIDC Trusted Publishing. Version bumped in `pyproject.toml`
and `src/agentx/__init__.py` before tagging.

## Installation

```bash
pip install --upgrade agentx-kit
```

Verify:

```python
import agentx
print(agentx.__version__)   # 0.17.0
```
