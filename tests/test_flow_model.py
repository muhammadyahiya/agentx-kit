"""Tests for agentx.flow.model — the shared Flow/FlowNode/FlowEdge shape."""
from __future__ import annotations

from agentx.flow.model import Flow, FlowEdge


def test_add_edge_dedups_and_increments_count() -> None:
    flow = Flow()
    e1 = flow.add_edge("a", "b")
    e2 = flow.add_edge("a", "b")
    assert e1 is e2
    assert e1.count == 2
    assert len(flow.edges) == 1


def test_successors_and_predecessors_are_o1_backed() -> None:
    flow = Flow()
    flow.add_edge("a", "b")
    flow.add_edge("a", "c")
    flow.add_edge("b", "c")
    assert set(flow.successors("a")) == {"b", "c"}
    assert flow.predecessors("c") == ["a", "b"] or set(flow.predecessors("c")) == {"a", "b"}
    assert flow.successors("nonexistent") == []
    assert flow.predecessors("nonexistent") == []


def test_direct_edges_assignment_rebuilds_adjacency() -> None:
    # static.py's _subgraph_from assigns `sub.edges = [...]` directly instead
    # of going through add_edge — successors/predecessors must reflect that
    # reassignment, not just edges added via add_edge.
    flow = Flow()
    flow.edges = [FlowEdge(src="x", dst="y"), FlowEdge(src="y", dst="z")]
    assert flow.successors("x") == ["y"]
    assert flow.successors("y") == ["z"]
    assert flow.predecessors("z") == ["y"]
    assert len(flow.edges) == 2


def test_add_edge_after_direct_assignment_still_dedups() -> None:
    flow = Flow()
    flow.edges = [FlowEdge(src="x", dst="y")]
    edge = flow.add_edge("x", "y")
    assert edge.count == 2
    assert len(flow.edges) == 1
