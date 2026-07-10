# agentx-kit v0.17.1 — Release Notes

**Released:** 2026-07-10
**PyPI:** https://pypi.org/project/agentx-kit/0.17.1/
**Git tag:** `v0.17.1`

---

## What's new

Bug-fix release, no new flags or public API changes.

### `agentx flow --serve`'s terminal box no longer crashes on a bad command

Typing a command in the log pane's command box (e.g. a typo like
`streamline run app.py` instead of `streamlit run app.py`) used to raise an
uncaught `FileNotFoundError` from `subprocess.Popen`, crashing the whole
ASGI request with a 500 and a full Python traceback dumped to the terminal.
It also used `shlex.split()` to parse the typed command before running it
directly — which is POSIX-only and silently mangles Windows paths (e.g.
`python C:\Users\me\main.py` became `python C:Usersmemain.py`).

Fixed by running arbitrary terminal-box commands through the OS's own shell
(`cmd.exe` on Windows, `/bin/sh` elsewhere) instead of parsing and
direct-executing them — exactly like typing the command in a real terminal:
quoting, `&&`, and pipes all work, cross-platform paths are handled
correctly, and a mistyped or missing command just prints its own "not
found" error to the log like a real shell would, with a nonzero exit code
— it can no longer crash the server. The existing "python `<file>.py`
routed through the package-aware runner" behavior (for relative-import
support + trace events) is unchanged.

### `agentx flow`/`agentx graph` ascii output no longer wraps mid-branch

On a narrow terminal, a deeply-nested project's long `module.Class.method`
names could get soft-wrapped by Rich mid-line, breaking the tree structure
instead of just letting the line extend past the visible width the way
`tree`/`ls` output does. Fixed by rendering with `soft_wrap=True`.

---

## Files changed

**New files:**

- `tests/test_flow_server.py` — 2 new tests reproducing the exact crash and
  confirming shell-based execution behaves like a real shell instead

**Modified files:**

- `src/agentx/flow/server.py` — arbitrary terminal-box commands now run via
  `subprocess.Popen(command, shell=True, ...)`; `Popen` wrapped in
  `try/except OSError` as defense-in-depth; the `python <file>.py`
  package-aware detection is now regex-based on the raw command string
  instead of `shlex.split`-based (avoiding the same Windows path issue)
- `src/agentx/cli.py` — `console.print(..., soft_wrap=True)` for
  `agentx flow`'s ascii/mermaid/dot output and `agentx graph`'s
  ascii/mermaid output
- `tests/test_flow_server.py` — updated the "bad command" test to expect
  shell-level error output instead of an HTTP 400 (matching the new,
  correct behavior)
- `README.md` — clarified that the terminal box runs through a real shell

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
print(agentx.__version__)   # 0.17.1
```
