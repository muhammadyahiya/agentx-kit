"""Shared graph model for ``agentx.flow`` — one shape produced by both the
static AST analyzer and the runtime tracer, and consumed by every renderer."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FlowNode:
    """One function/method/class/module in the flow graph."""

    name: str
    file: str | None = None
    lineno: int | None = None
    external: bool = False   # True if not defined in the analyzed file (stdlib/3rd-party)
    calls: int = 0           # runtime: number of times this function was actually invoked
    total_time: float = 0.0  # runtime: cumulative wall-clock seconds across all calls
    kind: str = "function"   # "package" | "module" | "class" | "function" | "external"
    module: str | None = None   # dotted module path this node lives in, e.g. "pkg.sub.mod"
    parent: str | None = None   # containing node's key (method's class, class's module, ...)


@dataclass
class FlowEdge:
    """A directed call edge: ``src`` calls ``dst``."""

    src: str
    dst: str
    count: int = 1   # how many times this exact edge was seen


@dataclass
class Flow:
    """A directed call graph: functions as nodes, call sites as edges.

    ``edges`` is a property backed by ``_edges`` plus a same-key index and
    adjacency lists — a plain ``list[FlowEdge]`` with a linear scan per
    ``add_edge``/``successors``/``predecessors`` call is O(n) per call and
    O(n^2) overall for a large project-wide graph (thousands of edges). The
    index/adjacency structures are rebuilt whenever ``edges`` is assigned
    directly (e.g. ``sub.edges = [...]`` when building a subgraph), so both
    construction paths stay consistent.
    """

    nodes: dict[str, FlowNode] = field(default_factory=dict)
    entry: str | None = None
    kind: str = "static"   # "static" (AST) | "runtime" (traced execution)
    scope: str = "file"    # "file" (single file/runtime graph) | "project" (whole directory)
    _edges: list[FlowEdge] = field(default_factory=list, init=False, repr=False, compare=False)
    _edge_index: dict[tuple[str, str], FlowEdge] = field(default_factory=dict, init=False, repr=False, compare=False)
    _out: dict[str, list[str]] = field(default_factory=dict, init=False, repr=False, compare=False)
    _in: dict[str, list[str]] = field(default_factory=dict, init=False, repr=False, compare=False)

    @property
    def edges(self) -> list[FlowEdge]:
        return self._edges

    @edges.setter
    def edges(self, value: list[FlowEdge]) -> None:
        self._edges = value
        self._edge_index = {(e.src, e.dst): e for e in value}
        out: dict[str, list[str]] = {}
        in_: dict[str, list[str]] = {}
        for e in value:
            out.setdefault(e.src, []).append(e.dst)
            in_.setdefault(e.dst, []).append(e.src)
        self._out = out
        self._in = in_

    def add_node(self, name: str, **kwargs) -> FlowNode:
        node = self.nodes.get(name)
        if node is None:
            node = FlowNode(name=name, **kwargs)
            self.nodes[name] = node
        return node

    def add_edge(self, src: str, dst: str) -> FlowEdge:
        key = (src, dst)
        existing = self._edge_index.get(key)
        if existing is not None:
            existing.count += 1
            return existing
        edge = FlowEdge(src=src, dst=dst)
        self._edges.append(edge)
        self._edge_index[key] = edge
        self._out.setdefault(src, []).append(dst)
        self._in.setdefault(dst, []).append(src)
        return edge

    def successors(self, name: str) -> list[str]:
        return list(self._out.get(name, []))

    def predecessors(self, name: str) -> list[str]:
        return list(self._in.get(name, []))


__all__ = ["Flow", "FlowNode", "FlowEdge"]
