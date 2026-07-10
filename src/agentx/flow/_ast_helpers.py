"""Shared AST-visitor helpers used by both single-file (:mod:`agentx.flow.static`)
and whole-project (:mod:`agentx.flow.project`) call-graph builders.

Kept in one place instead of one module importing the other's private
(underscore-prefixed) symbols — the two builders shared this call-collection
logic exactly, so a fix to one (e.g. not recursing into nested function/class
bodies) previously had to be duplicated by hand to stay in sync.
"""
from __future__ import annotations

import ast

from .model import Flow


def call_name(node: ast.expr) -> str | None:
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


class CallCollector(ast.NodeVisitor):
    """Collect call sites within one function's body, in source order."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def visit_Call(self, node: ast.Call) -> None:
        name = call_name(node.func)
        if name:
            self.calls.append(name)
        self.generic_visit(node)

    def _skip_nested_def(self, node: ast.AST) -> None:
        # Nested function/class defs are collected as their own nodes by the
        # caller's own function/class collector pass and get their own
        # CallCollector pass — recursing into them here would
        # double-attribute their calls to the enclosing function too (e.g. a
        # call inside `def inner()` would wrongly also show up as a call
        # made by `outer`).
        pass

    visit_FunctionDef = _skip_nested_def
    visit_AsyncFunctionDef = _skip_nested_def
    visit_ClassDef = _skip_nested_def


def subgraph_from(flow: Flow, start: str) -> Flow:
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


__all__ = ["call_name", "CallCollector", "subgraph_from"]
