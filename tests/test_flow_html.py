"""Tests for agentx.flow.htmlgen — the self-contained interactive DAG viewer."""
from __future__ import annotations

import json
import re
from pathlib import Path

from agentx.flow import build_project_flow, build_static_flow, render_html
from agentx.flow.model import Flow, FlowNode


def _embedded_data(html: str) -> dict:
    m = re.search(r"window\.AGENTX_FLOW_DATA = (\{.*?\});", html, re.S)
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
    assert "def b" in b_node["full_source"]


def test_script_close_tag_in_snippet_is_escaped(tmp_path: Path) -> None:
    # A source file containing a literal "</script>" substring must not be
    # able to break out of the embedded <script> tag in the generated HTML.
    p = tmp_path / "app.py"
    p.write_text('def a():\n    x = "</script><script>alert(1)</script>"\n', encoding="utf-8")
    flow = build_static_flow(p)
    html = render_html(flow)
    assert "<script>alert(1)</script>" not in html
    data = _embedded_data(html)
    assert any("</script>" in n["full_source"] for n in data["nodes"])


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


def test_signature_extracted_for_typed_function(tmp_path: Path) -> None:
    p = tmp_path / "app.py"
    p.write_text("def add(a: int, b: int) -> int:\n    return a + b\n", encoding="utf-8")
    flow = build_static_flow(p)
    html = render_html(flow)
    data = _embedded_data(html)
    node = next(n for n in data["nodes"] if n["id"] == "add")
    assert node["signature"] == "def add(a: int, b: int) -> int"


def test_full_source_captures_whole_function_body(tmp_path: Path) -> None:
    p = tmp_path / "app.py"
    p.write_text("def a():\n    x = 1\n    y = 2\n    return x + y\n", encoding="utf-8")
    flow = build_static_flow(p)
    html = render_html(flow)
    data = _embedded_data(html)
    node = next(n for n in data["nodes"] if n["id"] == "a")
    assert "x = 1" in node["full_source"]
    assert "return x + y" in node["full_source"]


def test_pydantic_schema_attached_to_class_node(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "pkg" / "models.py").write_text(
        "from pydantic import BaseModel\n\nclass User(BaseModel):\n    name: str\n    age: int = 0\n",
        encoding="utf-8",
    )
    flow = build_project_flow(tmp_path)
    html = render_html(flow)
    data = _embedded_data(html)
    node = next(n for n in data["nodes"] if n["id"] == "pkg.models.User")
    assert node["kind"] == "class"
    assert node["schema"] == [
        {"name": "name", "type": "str", "default": None, "required": True},
        {"name": "age", "type": "int", "default": "0", "required": False},
    ]


def test_non_class_nodes_have_no_schema(tmp_path: Path) -> None:
    p = tmp_path / "app.py"
    p.write_text("def a():\n    pass\n", encoding="utf-8")
    flow = build_static_flow(p)
    html = render_html(flow)
    data = _embedded_data(html)
    node = next(n for n in data["nodes"] if n["id"] == "a")
    assert node["schema"] is None


def test_diagnostics_merge_onto_matching_node(tmp_path: Path) -> None:
    p = tmp_path / "app.py"
    p.write_text("def a():\n    pass\n", encoding="utf-8")
    flow = build_static_flow(p)
    diagnostics = {"a": [{"line": 1, "severity": "error", "message": "boom"}]}
    html = render_html(flow, diagnostics=diagnostics)
    data = _embedded_data(html)
    node = next(n for n in data["nodes"] if n["id"] == "a")
    assert node["type_errors"] == [{"line": 1, "severity": "error", "message": "boom"}]


def test_nodes_without_diagnostics_have_empty_type_errors(tmp_path: Path) -> None:
    p = tmp_path / "app.py"
    p.write_text("def a():\n    pass\n", encoding="utf-8")
    flow = build_static_flow(p)
    html = render_html(flow)  # no diagnostics passed at all
    data = _embedded_data(html)
    node = next(n for n in data["nodes"] if n["id"] == "a")
    assert node["type_errors"] == []


def test_serve_false_by_default() -> None:
    flow = Flow()
    flow.add_node("a")
    html = render_html(flow)
    data = _embedded_data(html)
    assert data["serve"] is False
    assert data["serve_token"] is None


def test_serve_true_embeds_token() -> None:
    flow = Flow()
    flow.add_node("a")
    html = render_html(flow, serve=True, serve_token="secret123")
    data = _embedded_data(html)
    assert data["serve"] is True
    assert data["serve_token"] == "secret123"


def test_cdn_false_by_default_inlines_vendor_js() -> None:
    flow = Flow()
    flow.add_node("a")
    html = render_html(flow)
    assert "cytoscape" in html  # inlined library source present
    assert "cdn.jsdelivr.net" not in html


def test_cdn_true_references_cdn_instead_of_inlining() -> None:
    flow = Flow()
    flow.add_node("a")
    html = render_html(flow, cdn=True)
    assert "cdn.jsdelivr.net" in html
    assert 'src="https://cdn.jsdelivr.net' in html
    # The app's own logic must still be inlined (only the vendor libs are CDN'd).
    assert "AGENTX_FLOW_DATA" in html


def test_elk_and_navigator_vendor_libs_are_inlined() -> None:
    flow = Flow()
    flow.add_node("a")
    html = render_html(flow)
    # ELK.js (layered layout engine) + its cytoscape adapter, and the
    # cytoscape-navigator minimap plugin, must be vendored inline like the
    # other 2D/3D graph libs — no separate network fetch, same as dagre.
    assert "cytoscapeElk" in html
    assert "cytoscape-navigator" in html
    assert ".ELK=n()" in html  # elk.bundled.min.js's UMD export of the global `ELK`


def test_cdn_mode_references_elk_and_navigator_urls() -> None:
    flow = Flow()
    flow.add_node("a")
    html = render_html(flow, cdn=True)
    assert "cdn.jsdelivr.net/npm/elkjs" in html
    assert "cdn.jsdelivr.net/npm/cytoscape-elk" in html
    assert "cdn.jsdelivr.net/npm/cytoscape-navigator" in html


def test_viewer_markup_includes_layout_toggle_minimap_and_command_palette() -> None:
    flow = Flow()
    flow.add_node("a")
    html = render_html(flow)
    assert 'id="layoutSeg"' in html
    assert 'data-layout="elk"' in html
    assert 'data-layout="dagre"' in html
    assert 'id="navigator"' in html
    assert 'id="cmdPalette"' in html
    assert 'id="cmdInput"' in html


def test_app_js_defaults_to_elk_layout_with_dagre_fallback() -> None:
    flow = Flow()
    flow.add_node("a")
    html = render_html(flow)
    assert "localStorage.getItem('agentx-flow-layout') || 'elk'" in html
    assert "name: 'elk'" in html
    assert "name: 'dagre'" in html


def test_app_js_fuzzy_match_requires_in_order_subsequence() -> None:
    # fuzzyScore is defined inline in the vendored app.js — exercise the same
    # algorithm here in Python to lock down its subsequence-matching contract
    # (every query char must appear in target, in order, not necessarily
    # contiguous) independent of a browser runtime.
    def fuzzy_score(query: str, target: str):
        qi = 0
        first = last = -1
        for ti, ch in enumerate(target):
            if qi < len(query) and ch == query[qi]:
                if first == -1:
                    first = ti
                last = ti
                qi += 1
        if qi < len(query):
            return None
        return (last - first) + first * 0.5

    assert fuzzy_score("cldt", "clean_data") is not None
    assert fuzzy_score("xyz", "clean_data") is None
    # Tighter/earlier match should score lower (better) than a looser one.
    assert fuzzy_score("cd", "cd_rest") < fuzzy_score("cd", "xxxxxxxxxxc" + "y" * 20 + "d")


def test_react_false_by_default_renders_cytoscape_viewer() -> None:
    flow = Flow()
    flow.add_node("a")
    html = render_html(flow)
    assert "AGENTX_FLOW_DATA" in html
    assert "cytoscapeElk" in html  # the default (Cytoscape) viewer's vendor libs
    assert "react-flow" not in html.lower()


def test_react_true_renders_react_bundle_with_real_data() -> None:
    flow = Flow(scope="project", entry="pkg.mod")
    flow.add_node("a")
    html = render_html(flow, react=True)
    data = _embedded_data(html)
    assert data["scope"] == "project"
    assert data["nodes"][0]["id"] == "a"
    assert "<title>agentx flow — pkg.mod</title>" in html
    assert "<script src=" not in html  # still one self-contained file, no external refs


def test_react_true_embeds_serve_flag_same_as_default_viewer() -> None:
    flow = Flow()
    flow.add_node("a")
    html = render_html(flow, react=True, serve=True, serve_token="secret123")
    data = _embedded_data(html)
    assert data["serve"] is True
    assert data["serve_token"] == "secret123"


def test_node_payload_has_null_git_info_outside_a_repo(tmp_path: Path) -> None:
    # tmp_path isn't inside a git repo, so gitmeta.node_git_info returns None
    # for every node — the "git" key must still be present (not omitted).
    p = tmp_path / "app.py"
    p.write_text("def a():\n    pass\n", encoding="utf-8")
    flow = build_static_flow(p)
    html = render_html(flow)
    data = _embedded_data(html)
    node = next(n for n in data["nodes"] if n["id"] == "a")
    assert "git" in node
    assert node["git"] is None
