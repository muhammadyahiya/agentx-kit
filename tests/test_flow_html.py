"""Tests for agentx.flow.htmlgen — the self-contained interactive DAG viewer."""
from __future__ import annotations

import json
import re
from pathlib import Path

from agentx.flow import build_static_flow, render_html
from agentx.flow.model import Flow, FlowNode


def _embedded_data(html: str) -> dict:
    m = re.search(r"const DATA = (\{.*?\});\s*\n\s*const COLORS", html, re.S)
    assert m, "graph JSON payload not found in generated HTML"
    return json.loads(m.group(1))


def test_no_unreplaced_placeholders_leak_into_output() -> None:
    flow = Flow()
    flow.add_node("a")
    html = render_html(flow)
    for placeholder in ("__GRAPH_DATA__", "__APP_JS__", "__CSS__", "__VENDOR_SCRIPTS__", "__TITLE__"):
        assert placeholder not in html


def test_empty_flow_renders_friendly_message() -> None:
    html = render_html(Flow())
    assert "no functions found" in html
    data = _embedded_data(html)
    assert data["nodes"] == []


def test_graph_payload_round_trips_nodes_and_edges() -> None:
    flow = Flow()
    flow.add_node("a", kind="function")
    flow.add_node("b", kind="function")
    flow.add_edge("a", "b")
    html = render_html(flow)
    data = _embedded_data(html)
    ids = {n["id"] for n in data["nodes"]}
    assert ids == {"a", "b"}
    assert data["edges"][0]["source"] == "a"
    assert data["edges"][0]["target"] == "b"


def test_external_node_effective_kind_overrides_default() -> None:
    # static.py never sets `kind` on external nodes (they default to "function"),
    # only the legacy `external` bool — render_html must still color them as external.
    flow = Flow()
    flow.add_node("a", kind="function")
    flow.add_node("xgboost.fit", external=True)
    flow.add_edge("a", "xgboost.fit")
    html = render_html(flow)
    data = _embedded_data(html)
    ext_node = next(n for n in data["nodes"] if n["id"] == "xgboost.fit")
    assert ext_node["kind"] == "external"


def test_dangling_parent_reference_is_dropped() -> None:
    # A node whose `parent` isn't itself a real node must not be passed through
    # (cytoscape errors on a compound `parent` that doesn't resolve to a node).
    flow = Flow()
    flow.add_node("a", parent="does-not-exist")
    html = render_html(flow)
    data = _embedded_data(html)
    node = next(n for n in data["nodes"] if n["id"] == "a")
    assert node["parent"] is None


def test_source_snippet_embedded_for_real_file(tmp_path: Path) -> None:
    p = tmp_path / "app.py"
    p.write_text("def a():\n    pass\n\n\ndef b():\n    a()\n", encoding="utf-8")
    flow = build_static_flow(p, entry="b")
    html = render_html(flow)
    data = _embedded_data(html)
    b_node = next(n for n in data["nodes"] if n["id"] == "b")
    assert "def b" in b_node["snippet"]


def test_script_close_tag_in_snippet_is_escaped(tmp_path: Path) -> None:
    # A source file containing a literal "</script>" substring must not be
    # able to break out of the embedded <script> tag in the generated HTML.
    p = tmp_path / "app.py"
    p.write_text('def a():\n    x = "</script><script>alert(1)</script>"\n', encoding="utf-8")
    flow = build_static_flow(p)
    html = render_html(flow)
    assert "<script>alert(1)</script>" not in html
    data = _embedded_data(html)
    assert any("</script>" in n["snippet"] for n in data["nodes"])


def test_project_scope_flag_present_in_payload() -> None:
    flow = Flow(scope="project")
    flow.add_node("pkg", kind="package")
    html = render_html(flow)
    data = _embedded_data(html)
    assert data["scope"] == "project"


def test_vendor_scripts_are_inlined() -> None:
    flow = Flow()
    flow.add_node("a")
    html = render_html(flow)
    assert "cytoscape" in html
    assert "ForceGraph3D" in html
    assert "<script src=" not in html  # fully self-contained, no external refs
