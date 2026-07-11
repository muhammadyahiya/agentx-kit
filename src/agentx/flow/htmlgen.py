"""Render a :class:`~agentx.flow.model.Flow` as one self-contained, interactive
HTML file — the ``agentx flow --ui`` "side screen".

The output is a single portable HTML document (works via a plain ``file://``
URL, no server, no CDN, no Node/npm involved in producing or viewing it):
graph data + short source snippets are embedded as a JSON blob, and every JS
dependency (Cytoscape.js + ELK.js/cytoscape-elk for the default layered
layout, dagre/cytoscape-dagre as an alternate layout, cytoscape-navigator for
the minimap, three.js + 3d-force-graph for the experimental 3D toggle) is
vendored under ``flow/vendor/`` and inlined directly into the file.
Level-of-detail (Modules / Classes / Full) is computed ourselves in-page from
the node hierarchy rather than relying on a collapse/expand plugin, so
aggregated edges between collapsed nodes are always exactly the underlying
calls.
"""
from __future__ import annotations

import ast
import json
from functools import lru_cache
from pathlib import Path

import jinja2

from .model import Flow
from .schema import build_class_index, extract_pydantic_fields

_VENDOR_DIR = Path(__file__).resolve().parent / "vendor"
_VIEWER_DIR = Path(__file__).resolve().parent / "viewer"

# Load order matters: three.js before 3d-force-graph (peer global `THREE`),
# cytoscape before its dagre/elk/navigator extensions (peer global
# `cytoscape`), and ELK.js's bundle (defines global `ELK`) before
# cytoscape-elk (calls `factory(root["ELK"])` at load time).
_VENDOR_FILES = [
    "three.min.js",
    "3d-force-graph.min.js",
    "cytoscape.min.js",
    "elk.bundled.min.js",
    "cytoscape-elk.js",
    "dagre.min.js",
    "cytoscape-dagre.js",
    "cytoscape-navigator.js",
]

# CDN URL for each vendor file, same order/versions as the vendored copies —
# used by ``--cdn`` (opt-in: the default stays fully offline-capable).
_CDN_URLS = {
    "three.min.js": "https://cdn.jsdelivr.net/npm/three@0.152.2/build/three.min.js",
    "3d-force-graph.min.js": "https://cdn.jsdelivr.net/npm/3d-force-graph@1.71.4/dist/3d-force-graph.min.js",
    "cytoscape.min.js": "https://cdn.jsdelivr.net/npm/cytoscape@3.34.0/dist/cytoscape.min.js",
    "elk.bundled.min.js": "https://cdn.jsdelivr.net/npm/elkjs@0.9.3/lib/elk.bundled.js",
    "cytoscape-elk.js": "https://cdn.jsdelivr.net/npm/cytoscape-elk@1.2.0/cytoscape-elk.js",
    "dagre.min.js": "https://cdn.jsdelivr.net/npm/dagre@0.8.5/dist/dagre.min.js",
    "cytoscape-dagre.js": "https://cdn.jsdelivr.net/npm/cytoscape-dagre@2.5.0/cytoscape-dagre.js",
    "cytoscape-navigator.js": "https://cdn.jsdelivr.net/npm/cytoscape-navigator@2.0.2/cytoscape-navigator.js",
}

# Colorblind-safe, kind-coded palette (Okabe-Ito/Tol-muted derived).
_COLORS = {
    "function": "#4477AA",
    "class": "#CCBB44",
    "module": "#66CCEE",
    "package": "#66CCEE",
    "external": "#999999",
}


def _read_vendor(name: str) -> str:
    return (_VENDOR_DIR / name).read_text(encoding="utf-8")


def _read_viewer(name: str) -> str:
    return (_VIEWER_DIR / name).read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def _viewer_env() -> jinja2.Environment:
    """The viewer HTML is a real Jinja2 template (``viewer/viewer.html.j2``)
    instead of a Python string with ``__PLACEHOLDER__``/``str.replace`` —
    that chain was order-dependent (the app JS placeholder had to be filled
    in before the graph-data placeholder, since the JS itself used to embed
    that placeholder) and any future placeholder name colliding with content
    already substituted in would have been silently double-substituted.
    ``autoescape=False``: the substituted values are raw HTML/CSS/JS/JSON,
    not user-facing text that needs escaping — same trust model the old
    ``str.replace`` chain had."""
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(_VIEWER_DIR)), autoescape=False,
    )


def _get_lines(file: str | None, cache: dict[str, list[str] | None]) -> list[str] | None:
    """Read+split ``file`` into lines once per :func:`render_html` call — a
    project can have many nodes per file, so caching avoids re-reading it
    from disk once per node (on top of the once-per-file parse ``_get_tree``
    already avoids)."""
    if not file:
        return None
    if file not in cache:
        try:
            cache[file] = Path(file).read_text(encoding="utf-8").splitlines()
        except OSError:
            cache[file] = None
    return cache[file]


def _snippet(
    file: str | None, lineno: int | None, lines_cache: dict[str, list[str] | None], *, context: int = 4,
) -> str:
    """A few source lines around ``lineno`` — the fallback for nodes with no
    resolvable def/class (external calls, module/package nodes)."""
    if not file or not lineno:
        return ""
    lines = _get_lines(file, lines_cache)
    if lines is None:
        return ""
    start = max(0, lineno - 1 - context)
    end = min(len(lines), lineno - 1 + context + 1)
    return "\n".join(lines[start:end])


def _get_tree(file: str | None, cache: dict[str, ast.Module | None]) -> ast.Module | None:
    """Parse ``file`` once per :func:`render_html` call — a project can have
    many nodes per file, so caching avoids re-parsing it once per node."""
    if not file:
        return None
    if file not in cache:
        try:
            cache[file] = ast.parse(Path(file).read_text(encoding="utf-8"), filename=file)
        except (OSError, SyntaxError):
            cache[file] = None
    return cache[file]


def _find_def(tree: ast.Module, lineno: int) -> ast.AST | None:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.lineno == lineno:
            return node
    return None


def _extract_signature(file: str | None, lineno: int | None, cache: dict[str, ast.Module | None]) -> str | None:
    """The declared type-hinted signature, as written — e.g. ``def foo(x: int) -> str``."""
    tree = _get_tree(file, cache)
    if tree is None or lineno is None:
        return None
    node = _find_def(tree, lineno)
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return None
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    returns = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    return f"{prefix} {node.name}({ast.unparse(node.args)}){returns}"


def _full_source(
    file: str | None,
    lineno: int | None,
    tree_cache: dict[str, ast.Module | None],
    lines_cache: dict[str, list[str] | None],
) -> str:
    """The whole def/class body (using ``end_lineno``), not just a fixed
    context window — falls back to :func:`_snippet` when there's no
    resolvable def/class at this location."""
    tree = _get_tree(file, tree_cache)
    if tree is not None and lineno is not None:
        node = _find_def(tree, lineno)
        if node is not None and getattr(node, "end_lineno", None):
            lines = _get_lines(file, lines_cache)
            if lines is not None:
                return "\n".join(lines[node.lineno - 1 : node.end_lineno])
    return _snippet(file, lineno, lines_cache)


def _def_end_lineno(file: str | None, lineno: int | None, tree_cache: dict[str, ast.Module | None]) -> int | None:
    """The 1-indexed last line of the def/class starting at ``lineno``, if
    resolvable — lets the side panel's editor replace exactly the lines that
    ``_full_source`` displayed, no more and no less."""
    tree = _get_tree(file, tree_cache)
    if tree is None or lineno is None:
        return None
    node = _find_def(tree, lineno)
    return getattr(node, "end_lineno", None) if node is not None else None


def _payload(flow: Flow, diagnostics: dict[str, list[dict]] | None = None) -> dict:
    tree_cache: dict[str, ast.Module | None] = {}
    lines_cache: dict[str, list[str] | None] = {}
    class_index_cache: dict[str, dict[int, ast.ClassDef]] = {}
    nodes = []
    for name, node in flow.nodes.items():
        kind = "external" if node.external else node.kind
        schema = None
        if kind == "class":
            tree = _get_tree(node.file, tree_cache)
            if tree is not None and node.lineno is not None:
                if node.file not in class_index_cache:
                    class_index_cache[node.file] = build_class_index(tree)
                schema = extract_pydantic_fields(tree, node.lineno, class_index_cache[node.file])
        nodes.append({
            "id": name,
            "label": name.rsplit(".", 1)[-1],
            "kind": kind,
            "module": node.module,
            "parent": node.parent if node.parent in flow.nodes else None,
            "file": node.file,
            "lineno": node.lineno,
            "end_lineno": _def_end_lineno(node.file, node.lineno, tree_cache),
            "calls": node.calls,
            "total_time": node.total_time,
            "full_source": _full_source(node.file, node.lineno, tree_cache, lines_cache),
            "signature": _extract_signature(node.file, node.lineno, tree_cache),
            "schema": schema,
            "type_errors": (diagnostics or {}).get(name, []),
        })
    edges = [
        {"id": f"e{i}", "source": e.src, "target": e.dst, "count": e.count}
        for i, e in enumerate(flow.edges)
    ]
    return {
        "scope": flow.scope,
        "kind": flow.kind,
        "entry": flow.entry,
        "colors": _COLORS,
        "nodes": nodes,
        "edges": edges,
    }


def render_html(
    flow: Flow,
    *,
    diagnostics: dict[str, list[dict]] | None = None,
    serve: bool = False,
    serve_token: str | None = None,
    cdn: bool = False,
) -> str:
    """Render ``flow`` as one complete, self-contained HTML document.

    Args:
        diagnostics: optional ``{node_id: [{"line", "severity", "message"}, ...]}``
            from :func:`agentx.flow.typecheck.map_diagnostics_to_nodes`
            (``agentx flow --typecheck``), merged onto each node.
        serve: when True, the page includes the Run/Stop live-execution
            controls that talk to the ``agentx flow --serve`` backend
            (:mod:`agentx.flow.server`) instead of being a passive view.
        serve_token: the per-server random token required on `--serve`'s API
            endpoints; embedded in the page so its own JS can attach it.
        cdn: reference the 2D/3D graph libraries via CDN ``<script src>``
            tags instead of inlining ~2MB of vendored JS into the file.
            Off by default — the point of ``--ui`` is a single file that
            still works from a plain ``file://`` URL with no network access.
    """
    payload = _payload(flow, diagnostics)
    payload["serve"] = serve
    payload["serve_token"] = serve_token
    payload_json = json.dumps(payload).replace("</", "<\\/")
    if cdn:
        vendor_scripts = "\n".join(f'<script src="{_CDN_URLS[name]}"></script>' for name in _VENDOR_FILES)
    else:
        vendor_scripts = "\n".join(
            f"<script>\n{_read_vendor(name)}\n</script>" for name in _VENDOR_FILES
        )
    title = f"agentx flow — {flow.entry or flow.scope}"
    # Monaco (the side panel's code editor) is ~5MB — only load it in --serve
    # mode, where editing is actually possible (there's a backend to save
    # to). The offline --ui file stays a single lightweight document with a
    # read-only <pre> panel, same as before.
    monaco_scripts = (
        '<script src="https://cdn.jsdelivr.net/npm/monaco-editor@0.45.0/min/vs/loader.js"></script>\n'
        '<script>window.AGENTX_MONACO_VS_URL = "https://cdn.jsdelivr.net/npm/monaco-editor@0.45.0/min/vs";</script>'
        if serve else ""
    )
    template = _viewer_env().get_template("viewer.html.j2")
    return template.render(
        title=title,
        css=_CSS,
        vendor_scripts=vendor_scripts,
        monaco_scripts=monaco_scripts,
        app_js=_read_viewer("app.js"),
        graph_data=payload_json,
    )


_CSS = """
:root {
  --bg: #ffffff; --fg: #1a1a1a; --panel-bg: #f7f7f9; --border: #ddd;
  --accent: #4477AA; --muted: #888;
}
@media (prefers-color-scheme: dark) {
  :root { --bg: #1e1f22; --fg: #e8e8e8; --panel-bg: #26272b; --border: #3a3b3f; --muted: #999; }
}
html.dark { --bg: #1e1f22; --fg: #e8e8e8; --panel-bg: #26272b; --border: #3a3b3f; --muted: #999; }
html.light { --bg: #ffffff; --fg: #1a1a1a; --panel-bg: #f7f7f9; --border: #ddd; --muted: #888; }
* { box-sizing: border-box; }
body { margin: 0; font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; background: var(--bg); color: var(--fg); }
#app { display: flex; flex-direction: column; height: 100vh; }
header { display: flex; align-items: center; gap: 10px; padding: 8px 12px; border-bottom: 1px solid var(--border); flex-wrap: wrap; }
header h1 { font-size: 14px; font-weight: 600; margin: 0 12px 0 0; white-space: nowrap; }
header input[type=text] { background: var(--panel-bg); border: 1px solid var(--border); color: var(--fg); border-radius: 5px; padding: 5px 8px; font-size: 12px; width: 180px; }
.btn { background: var(--panel-bg); border: 1px solid var(--border); color: var(--fg); border-radius: 5px; padding: 5px 9px; font-size: 12px; cursor: pointer; }
.btn.active { background: var(--accent); color: #fff; border-color: var(--accent); }
.seg { display: flex; border: 1px solid var(--border); border-radius: 5px; overflow: hidden; }
.seg .btn { border: none; border-radius: 0; border-right: 1px solid var(--border); }
.seg .btn:last-child { border-right: none; }
.legend { display: flex; gap: 6px; font-size: 11px; }
.legend .chip { display: flex; align-items: center; gap: 4px; cursor: pointer; padding: 3px 7px; border-radius: 10px; border: 1px solid var(--border); user-select: none; }
.legend .chip.off { opacity: 0.35; }
.swatch { width: 9px; height: 9px; border-radius: 50%; display: inline-block; }
main { flex: 1; display: flex; min-height: 0; }
#cy, #graph3d { flex: 1; height: 100%; }
#empty { flex: 1; display: flex; align-items: center; justify-content: center; color: var(--muted); font-size: 14px; }
#panel { width: 320px; border-left: 1px solid var(--border); padding: 12px; overflow: auto; font-size: 12px; background: var(--panel-bg); }
#panel h2 { font-size: 13px; margin: 0 0 6px; word-break: break-all; }
#panel .meta { color: var(--muted); margin-bottom: 8px; }
#panel pre { background: var(--bg); border: 1px solid var(--border); border-radius: 5px; padding: 8px; overflow: auto; font-size: 11px; line-height: 1.5; }
#panel .hint { color: var(--muted); }
#panel .sig { background: var(--bg); border: 1px solid var(--border); border-radius: 5px; padding: 6px 8px; margin-bottom: 8px; font-size: 11px; overflow: auto; }
#panel .section-title { font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: 0.03em; color: var(--muted); margin: 10px 0 4px; }
#panel .diag-list { margin: 0 0 8px; padding-left: 16px; font-size: 11px; }
#panel .diag-error { color: #EE6677; }
#panel .diag-warning { color: #CCBB44; }
#panel .diag-note { color: var(--muted); }
#panel .schema-table { width: 100%; border-collapse: collapse; font-size: 11px; margin-bottom: 8px; }
#panel .schema-table th, #panel .schema-table td { text-align: left; padding: 3px 6px; border-bottom: 1px solid var(--border); }
#panel .schema-table th { color: var(--muted); font-weight: 600; }
label.chk { display: flex; align-items: center; gap: 4px; font-size: 12px; }
.btn.run { background: #2ca02c; color: #fff; border-color: #2ca02c; }
.btn.stop { background: #EE6677; color: #fff; border-color: #EE6677; }
#logPane { display: none; flex-direction: column; height: 200px; border-top: 1px solid var(--border); background: #16171a; }
#logPane .log-header { display: flex; justify-content: space-between; align-items: center; padding: 4px 10px; font-size: 11px; color: #aaa; border-bottom: 1px solid #2a2b2f; }
#logPane .btn-mini { background: none; border: none; color: #aaa; cursor: pointer; font-size: 13px; padding: 0 6px; }
#logBody { flex: 1; overflow: auto; padding: 6px 10px; font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 11.5px; }
.log-line { white-space: pre-wrap; line-height: 1.5; }
#panel .src-toolbar { display: flex; align-items: center; gap: 6px; margin: 10px 0 4px; }
#panel .src-toolbar .section-title { margin: 0; flex: 1; }
#panel .src-toolbar .btn { padding: 2px 8px; font-size: 10px; }
#panel .btn.save { background: #2ca02c; color: #fff; border-color: #2ca02c; }
#panel .btn.cancel { background: #EE6677; color: #fff; border-color: #EE6677; }
#panel .stale-badge { display: inline-block; margin-left: 6px; padding: 1px 6px; border-radius: 8px; font-size: 10px; font-weight: 600; background: #CCBB44; color: #1a1a1a; }
#monacoHost { height: 320px; border: 1px solid var(--border); border-radius: 5px; overflow: hidden; }
.log-stdout { color: #d8d8d8; }
.log-stderr { color: #ff8080; }
.log-trace { color: #7ec8e3; }
.log-info { color: #999; font-style: italic; }
.term-bar { display: flex; align-items: center; gap: 6px; padding: 6px 10px; border-top: 1px solid #2a2b2f; }
.term-prompt { color: #2ca02c; font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 12px; }
#termInput { flex: 1; background: #0f1012; border: 1px solid #2a2b2f; color: #d8d8d8; border-radius: 4px; padding: 5px 8px; font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 12px; }
#termInput:disabled { opacity: 0.5; }
#cy { position: relative; }
#navigator.cytoscape-navigator { position: absolute !important; bottom: 10px; right: 10px; top: auto !important; left: auto !important;
  width: 180px; height: 130px; border: 1px solid var(--border); border-radius: 5px; background: var(--panel-bg); opacity: 0.92; z-index: 50; }
.cytoscape-navigatorView { background: var(--accent); opacity: 0.35; }
.cytoscape-navigatorOverlay { z-index: 51; }
#cmdPalette { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.35); z-index: 999; align-items: flex-start; justify-content: center; padding-top: 12vh; }
#cmdPalette.open { display: flex; }
#cmdPaletteBox { width: 460px; max-width: 90vw; background: var(--panel-bg); border: 1px solid var(--border); border-radius: 8px; box-shadow: 0 12px 40px rgba(0,0,0,0.35); overflow: hidden; }
#cmdInput { width: 100%; box-sizing: border-box; padding: 12px 14px; font-size: 14px; border: none; border-bottom: 1px solid var(--border); background: var(--bg); color: var(--fg); }
#cmdInput:focus { outline: none; }
#cmdResults { max-height: 320px; overflow: auto; }
.cmd-item { display: flex; align-items: center; gap: 8px; padding: 8px 14px; font-size: 12.5px; cursor: pointer; }
.cmd-item .swatch { flex: none; width: 9px; height: 9px; border-radius: 50%; }
.cmd-item .cmd-id { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cmd-item .cmd-kind { color: var(--muted); font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.03em; }
.cmd-item.active { background: var(--accent); color: #fff; }
.cmd-item.active .cmd-kind { color: rgba(255,255,255,0.75); }
.cmd-empty { padding: 14px; color: var(--muted); font-size: 12px; text-align: center; }
"""


__all__ = ["render_html"]
