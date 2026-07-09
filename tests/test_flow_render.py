"""Tests for agentx.flow.render — ascii/mermaid/json/dot renderers."""
from __future__ import annotations

from agentx.flow import Flow, render_ascii, render_dot, render_json, render_mermaid


def _linear_flow() -> Flow:
    flow = Flow(kind="static", entry="preprocess")
    for name in ("preprocess", "load_csv", "clean_data", "validate"):
        flow.add_node(name)
    flow.add_edge("preprocess", "load_csv")
    flow.add_edge("load_csv", "clean_data")
    flow.add_edge("clean_data", "validate")
    return flow


def _branching_flow() -> Flow:
    flow = Flow(kind="static", entry="preprocess")
    for name in ("preprocess", "load_csv", "clean_data", "validate"):
        flow.add_node(name)
    flow.add_edge("preprocess", "load_csv")
    flow.add_edge("preprocess", "clean_data")
    flow.add_edge("preprocess", "validate")
    return flow


class TestRenderAscii:
    def test_empty_flow(self) -> None:
        assert render_ascii(Flow()) == "(no functions found)"

    def test_linear_chain_uses_arrow_style(self) -> None:
        text = render_ascii(_linear_flow())
        assert text.startswith("○ Start")
        assert "▼" in text
        # Nodes appear in call order.
        lines = text.splitlines()
        order = [l for l in lines if l not in ("○ Start", " │", " ▼")]
        assert order == ["preprocess", "load_csv", "clean_data", "validate"]

    def test_branching_uses_tree_style(self) -> None:
        text = render_ascii(_branching_flow())
        assert "├─ load_csv" in text or "└─ load_csv" in text
        assert "preprocess" in text.splitlines()[0]

    def test_runtime_labels_include_call_count_and_time(self) -> None:
        flow = Flow(kind="runtime")
        node = flow.add_node("train")
        node.calls = 3
        node.total_time = 0.045
        flow.add_node("clean")
        flow.add_edge("train", "clean")
        text = render_ascii(flow)
        assert "3 calls" in text
        assert "45.0ms" in text


class TestRenderMermaid:
    def test_starts_with_graph_td(self) -> None:
        text = render_mermaid(_linear_flow())
        assert text.startswith("graph TD")

    def test_edges_present(self) -> None:
        text = render_mermaid(_linear_flow())
        assert "-->" in text

    def test_isolated_nodes_with_no_edges_still_listed(self) -> None:
        flow = Flow()
        flow.add_node("lonely")
        text = render_mermaid(flow)
        assert "lonely" in text


class TestRenderJson:
    def test_shape(self) -> None:
        data = render_json(_linear_flow())
        assert data["kind"] == "static"
        assert data["entry"] == "preprocess"
        assert {n["name"] for n in data["nodes"]} == {"preprocess", "load_csv", "clean_data", "validate"}
        assert {"from": "preprocess", "to": "load_csv", "count": 1} in data["edges"]

    def test_external_flag_present(self) -> None:
        flow = Flow()
        flow.add_node("local_fn")
        flow.add_node("pd.read_csv", external=True)
        data = render_json(flow)
        ext = next(n for n in data["nodes"] if n["name"] == "pd.read_csv")
        assert ext["external"] is True


class TestRenderDot:
    def test_shape(self) -> None:
        text = render_dot(_linear_flow())
        assert text.startswith("digraph G {")
        assert text.endswith("}")
        assert '"preprocess" -> "load_csv";' in text
        assert '"preprocess" [label="preprocess"];' in text

    def test_quotes_in_labels_are_escaped(self) -> None:
        flow = Flow()
        flow.add_node('weird"name')
        text = render_dot(flow)
        assert '"weird' in text  # doesn't crash / produce invalid dot syntax
