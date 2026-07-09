"""Shared graph model for ``agentx.flow`` — one shape produced by both the
static AST analyzer and the runtime tracer, and consumed by every renderer."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FlowNode:
    """One function/method in the flow graph."""

    name: str
    file: str | None = None
    lineno: int | None = None
    external: bool = False   # True if not defined in the analyzed file (stdlib/3rd-party)
    calls: int = 0           # runtime: number of times this function was actually invoked
    total_time: float = 0.0  # runtime: cumulative wall-clock seconds across all calls


@dataclass
class FlowEdge:
    """A directed call edge: ``src`` calls ``dst``."""

    src: str
    dst: str
    count: int = 1   # how many times this exact edge was seen


@dataclass
class Flow:
    """A directed call graph: functions as nodes, call sites as edges."""

    nodes: dict[str, FlowNode] = field(default_factory=dict)
    edges: list[FlowEdge] = field(default_factory=list)
    entry: str | None = None
    kind: str = "static"   # "static" (AST) | "runtime" (traced execution)

    def add_node(self, name: str, **kwargs) -> FlowNode:
        node = self.nodes.get(name)
        if node is None:
            node = FlowNode(name=name, **kwargs)
            self.nodes[name] = node
        return node

    def add_edge(self, src: str, dst: str) -> FlowEdge:
        for e in self.edges:
            if e.src == src and e.dst == dst:
                e.count += 1
                return e
        edge = FlowEdge(src=src, dst=dst)
        self.edges.append(edge)
        return edge

    def successors(self, name: str) -> list[str]:
        return [e.dst for e in self.edges if e.src == name]

    def predecessors(self, name: str) -> list[str]:
        return [e.src for e in self.edges if e.dst == name]


__all__ = ["Flow", "FlowNode", "FlowEdge"]
