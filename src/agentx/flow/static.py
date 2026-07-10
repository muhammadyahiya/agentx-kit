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

from .model import Flow


def _call_name(node: ast.expr) -> str | None:
    """Best-effort dotted name for a call target, e.g. ``pd.read_csv`` or ``clean``."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parts = [node.attr]
        cur: ast.expr = node.value
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name):
            parts.append(cur.id)
            return ".".join(reversed(parts))
        return node.attr   # base isn't a simple name (e.g. a call result) — use the method name
    return None


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


class _CallCollector(ast.NodeVisitor):
    """Pass 2: collect call sites within one function's body, in source order."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def visit_Call(self, node: ast.Call) -> None:
        name = _call_name(node.func)
        if name:
            self.calls.append(name)
        self.generic_visit(node)


def _subgraph_from(flow: Flow, start: str) -> Flow:
    """BFS from ``start`` following outgoing edges; return the reachable subgraph."""
    reachable = {start}
    frontier = [start]
    while frontier:
        cur = frontier.pop()
        for name in flow.successors(cur):
            if name not in reachable:
                reachable.add(name)
                frontier.append(name)
    sub = Flow(kind=flow.kind, entry=start)
    sub.nodes = {name: flow.nodes[name] for name in reachable if name in flow.nodes}
    sub.edges = [e for e in flow.edges if e.src in reachable and e.dst in reachable]
    return sub


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
    source = p.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(p))

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
        calls = _CallCollector()
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
    module_calls = _CallCollector()
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
        return _subgraph_from(flow, target)

    flow.entry = inferred_entry
    return flow


__all__ = ["build_static_flow"]
