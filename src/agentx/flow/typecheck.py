"""Optional, opt-in type-checking pass for the flow viewer (``agentx flow --typecheck``).

Wraps `mypy <https://mypy.readthedocs.io/>`_'s in-process API — pure Python,
no Node/toolchain requirement, unlike pyright — and maps its file:line
diagnostics onto the nearest enclosing :class:`~agentx.flow.model.FlowNode`
so the HTML viewer can show them per node. Requires the optional
``agentx-kit[typecheck]`` extra; importing this module without mypy
installed raises :class:`ImportError` (the CLI guards this with a friendly
install hint before importing).
"""
from __future__ import annotations

import re
from pathlib import Path

from .model import Flow

_LINE_RE = re.compile(r"^(?P<file>.+?):(?P<line>\d+):\s*(?P<severity>error|warning|note):\s*(?P<message>.+)$")


def run_mypy(path: str | Path) -> dict[str, list[dict]]:
    """Run mypy against ``path`` (file or directory) and return diagnostics
    grouped by absolute file path: ``{file: [{"line", "severity", "message"}, ...]}``.

    Raises ``ImportError`` if mypy isn't installed — callers should guard
    this the same way the CLI does for every other optional dependency.
    """
    from mypy import api  # noqa: PLC0415 — intentional: mypy is optional

    # --no-incremental: this is a one-shot check on an arbitrary path, not
    # iterative project development. mypy's on-disk incremental cache is
    # keyed loosely enough that unrelated files sharing a basename (e.g. two
    # different temp-dir "app.py"s) can serve each other's stale results —
    # skip the cache entirely so every run is self-contained and correct.
    #
    # --ignore-missing-imports: agentx-kit itself (and most third-party libs
    # a user's project imports) ships no `py.typed` marker, so without this
    # every single project that imports `agentx.*` would get a spurious
    # "missing library stubs" error drowning out real diagnostics about the
    # user's own code.
    stdout, _stderr, _status = api.run([
        str(path), "--follow-imports=silent", "--show-error-codes",
        "--no-error-summary", "--no-incremental", "--ignore-missing-imports",
    ])

    diagnostics: dict[str, list[dict]] = {}
    for line in stdout.splitlines():
        m = _LINE_RE.match(line)
        if not m:
            continue
        file = str(Path(m.group("file")).resolve())
        diagnostics.setdefault(file, []).append({
            "line": int(m.group("line")),
            "severity": m.group("severity"),
            "message": m.group("message"),
        })
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


__all__ = ["run_mypy", "map_diagnostics_to_nodes"]
