"""Optional, opt-in code-quality pass for the flow viewer (``agentx flow --typecheck``).

Runs `ruff <https://docs.astral.sh/ruff/>`_ (lint) and
`ty <https://github.com/astral-sh/ty>`_ (Astral's type checker) as
subprocesses and maps their file:line diagnostics onto the nearest enclosing
:class:`~agentx.flow.model.FlowNode` so the HTML viewer can show them per
node. Both are Rust binaries with no stable in-process Python API (unlike
mypy's ``mypy.api.run()``), so they're invoked as ``python -m ruff``/
``python -m ty`` subprocesses with machine-readable output instead. Requires
the optional ``agentx-kit[typecheck]`` extra; calling :func:`run_typecheck`
without ruff/ty installed raises :class:`ImportError` (the CLI guards this
with a friendly install hint before calling it).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from .model import Flow

# ty reports GitLab Code Quality severities (info/minor/major/critical/blocker);
# the viewer only styles "error"/"warning"/"note" (see htmlgen.py's .diag-*
# CSS classes), so map down to that 3-value vocabulary.
_TY_SEVERITY_MAP = {
    "blocker": "error",
    "critical": "error",
    "major": "error",
    "minor": "warning",
    "info": "note",
}


def _run_ruff(path: str | Path) -> dict[str, list[dict]]:
    """Run ``ruff check`` (lint) against ``path`` and return diagnostics
    grouped by absolute file path."""
    proc = subprocess.run(  # noqa: S603 — fixed argv, no shell, no user input
        [sys.executable, "-m", "ruff", "check", str(path), "--output-format", "json", "--exit-zero"],
        capture_output=True, text=True,
    )
    try:
        items = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return {}

    diagnostics: dict[str, list[dict]] = {}
    for item in items:
        file = str(Path(item["filename"]).resolve())
        diagnostics.setdefault(file, []).append({
            "line": item["location"]["row"],
            "severity": item.get("severity") or "warning",
            "message": f"{item['code']} {item['message']}",
            "tool": "ruff",
        })
    return diagnostics


def _run_ty(path: str | Path) -> dict[str, list[dict]]:
    """Run ``ty check`` (type checking) against ``path`` and return
    diagnostics grouped by absolute file path."""
    proc = subprocess.run(  # noqa: S603 — fixed argv, no shell, no user input
        [sys.executable, "-m", "ty", "check", str(path), "--output-format", "gitlab", "--exit-zero"],
        capture_output=True, text=True,
    )
    try:
        items = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return {}

    diagnostics: dict[str, list[dict]] = {}
    for item in items:
        file = str(Path(item["location"]["path"]).resolve())
        diagnostics.setdefault(file, []).append({
            "line": item["location"]["positions"]["begin"]["line"],
            "severity": _TY_SEVERITY_MAP.get(item.get("severity", "major"), "error"),
            "message": item["description"],
            "tool": "ty",
        })
    return diagnostics


def run_typecheck(path: str | Path) -> dict[str, list[dict]]:
    """Run ruff (lint) and ty (type check) against ``path`` (file or
    directory) and return merged diagnostics grouped by absolute file path:
    ``{file: [{"line", "severity", "message", "tool"}, ...]}``.

    Raises ``ImportError`` if ruff or ty aren't installed — callers should
    guard this the same way the CLI does for every other optional dependency.
    """
    import ruff  # noqa: F401, PLC0415 — intentional: optional dep, checked here
    import ty  # noqa: F401, PLC0415 — intentional: optional dep, checked here

    diagnostics: dict[str, list[dict]] = {}
    for file, diags in _run_ruff(path).items():
        diagnostics.setdefault(file, []).extend(diags)
    for file, diags in _run_ty(path).items():
        diagnostics.setdefault(file, []).extend(diags)
    return diagnostics


def map_diagnostics_to_nodes(flow: Flow, file_diagnostics: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """Assign each file:line diagnostic to the node in that file whose
    ``lineno`` is the closest one at-or-before the diagnostic's line — the
    same "nearest enclosing definition" heuristic a debugger uses to map a
    line back to a function."""
    nodes_by_file: dict[str, list[tuple[int, str]]] = {}
    for name, node in flow.nodes.items():
        if node.file is None or node.lineno is None:
            continue
        nodes_by_file.setdefault(str(Path(node.file).resolve()), []).append((node.lineno, name))

    for entries in nodes_by_file.values():
        entries.sort()

    result: dict[str, list[dict]] = {}
    for file, diags in file_diagnostics.items():
        entries = nodes_by_file.get(file)
        if not entries:
            continue
        for diag in diags:
            target = None
            for lineno, name in entries:
                if lineno <= diag["line"]:
                    target = name
                else:
                    break
            if target is not None:
                result.setdefault(target, []).append(diag)
    return result


__all__ = ["run_typecheck", "map_diagnostics_to_nodes"]
