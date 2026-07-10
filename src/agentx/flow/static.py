"""Static, AST-based function-call graph builder.

Parses a Python file with the ``ast`` module — nothing is imported or
executed. One node per function/method definition; one edge per call site
found inside another function's body (or at module scope, e.g. the
``if __name__ == "__main__": main()`` pattern). Call resolution is
best-effort, the same trade-off ``code2flow``/``pyan`` make: dynamic dispatch,
calls through variables holding functions, and calls resolved only at runtime
are not tracked (a ``.fit()`` call on a variable resolves to a bare ``fit``
node, not a specific class's method).
"""
from __future__ import annotations

import ast
from pathlib import Path

from ._ast_helpers import CallCollector, subgraph_from
from .model import Flow


class _FunctionCollector(ast.NodeVisitor):
    """Pass 1: register every function/method definition with a qualified name."""

    def __init__(self) -> None:
        self.functions: dict[str, ast.AST] = {}
        self._scope: list[str] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._scope.append(node.name)
        self.generic_visit(node)
        self._scope.pop()

    def _visit_func(self, node) -> None:
        qual = ".".join([*self._scope, node.name])
        self.functions[qual] = node
        self._scope.append(node.name)
        self.generic_visit(node)
        self._scope.pop()

    visit_FunctionDef = _visit_func
    visit_AsyncFunctionDef = _visit_func


def build_static_flow(path: str | Path, *, entry: str | None = None, include_external: bool = True) -> Flow:
    """Build a static call-graph :class:`~agentx.flow.model.Flow` for a Python file.

    Args:
        path: Path to a ``.py`` file.
        entry: If given, return only the subgraph reachable from this function
            name (bare or dotted). Raises ``ValueError`` if not found.
        include_external: Include edges to calls that don't resolve to a
            function defined in this file (stdlib/3rd-party calls, shown as
            leaf nodes tagged ``external=True``). Set False for a local-only
            call graph.
    """
    p = Path(path)
    try:
        source = p.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Could not read {p}: {exc}") from exc
    try:
        tree = ast.parse(source, filename=str(p))
    except SyntaxError as exc:
        raise ValueError(f"Syntax error in {p}: {exc.msg} (line {exc.lineno})") from exc

    collector = _FunctionCollector()
    collector.visit(tree)
    local_names = set(collector.functions)
    # Map bare names to their qualname (e.g. "clean_data" -> "clean_data", or
    # "clean_data" -> "MyClass.clean_data" for a method) — first match wins.
    bare_to_qual: dict[str, str] = {}
    for qual in local_names:
        bare_to_qual.setdefault(qual.rsplit(".", 1)[-1], qual)

    def _resolve(called: str) -> str | None:
        if called in local_names:
            return called
        if "." in called:
            prefix, _, bare = called.rpartition(".")
            # `self.step()` / `cls.step()` — resolve the method by its bare name.
            # Other dotted calls (e.g. `pd.read_csv`) are left as external rather
            # than risking a false-positive match against an unrelated local
            # function that happens to share the same bare name.
            if prefix in ("self", "cls"):
                return bare_to_qual.get(bare)
            return None
        return bare_to_qual.get(called)

    flow = Flow(kind="static")
    for qual, node in collector.functions.items():
        flow.add_node(qual, file=str(p), lineno=getattr(node, "lineno", None))

    for qual, node in collector.functions.items():
        calls = CallCollector()
        for stmt in node.body:
            calls.visit(stmt)
        for called in calls.calls:
            resolved = _resolve(called)
            if resolved:
                flow.add_edge(qual, resolved)
            elif include_external:
                flow.add_node(called, external=True)
                flow.add_edge(qual, called)

    # Module-level calls (outside any function/class) — captures the
    # `if __name__ == "__main__": main()` entry-point pattern.
    module_calls = CallCollector()
    for stmt in tree.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        module_calls.visit(stmt)
    inferred_entry: str | None = None
    for called in module_calls.calls:
        resolved = _resolve(called)
        if resolved:
            flow.add_node("__main__")
            flow.add_edge("__main__", resolved)
            inferred_entry = inferred_entry or "__main__"
        elif include_external:
            flow.add_node("__main__")
            flow.add_node(called, external=True)
            flow.add_edge("__main__", called)
            inferred_entry = inferred_entry or "__main__"

    if entry:
        target = entry if entry in flow.nodes else bare_to_qual.get(entry)
        if target is None:
            raise ValueError(f"Function {entry!r} not found in {p}")
        return subgraph_from(flow, target)

    flow.entry = inferred_entry
    return flow


__all__ = ["build_static_flow"]
