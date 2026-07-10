"""Render a :class:`~agentx.flow.model.Flow` as one self-contained, interactive
HTML file — the ``agentx flow --ui`` "side screen".

The output is a single portable HTML document (works via a plain ``file://``
URL, no server, no CDN, no Node/npm involved in producing or viewing it):
graph data + short source snippets are embedded as a JSON blob, and every JS
dependency (Cytoscape.js + dagre + cytoscape-dagre for the 2D layered view,
three.js + 3d-force-graph for the experimental 3D toggle) is vendored under
``flow/vendor/`` and inlined directly into the file. Level-of-detail
(Modules / Classes / Full) is computed ourselves in-page from the node
hierarchy rather than relying on a collapse/expand plugin, so aggregated
edges between collapsed nodes are always exactly the underlying calls.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

from .model import Flow
from .schema import extract_pydantic_fields

_VENDOR_DIR = Path(__file__).resolve().parent / "vendor"

# Load order matters: three.js before 3d-force-graph (peer global `THREE`),
# cytoscape before its dagre layout extension (peer global `cytoscape`).
_VENDOR_FILES = [
    "three.min.js",
    "3d-force-graph.min.js",
    "cytoscape.min.js",
    "dagre.min.js",
    "cytoscape-dagre.js",
]

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


def _snippet(file: str | None, lineno: int | None, *, context: int = 4) -> str:
    """A few source lines around ``lineno`` — the fallback for nodes with no
    resolvable def/class (external calls, module/package nodes)."""
    if not file or not lineno:
        return ""
    try:
        lines = Path(file).read_text(encoding="utf-8").splitlines()
    except OSError:
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


def _full_source(file: str | None, lineno: int | None, cache: dict[str, ast.Module | None]) -> str:
    """The whole def/class body (using ``end_lineno``), not just a fixed
    context window — falls back to :func:`_snippet` when there's no
    resolvable def/class at this location."""
    tree = _get_tree(file, cache)
    if tree is not None and lineno is not None:
        node = _find_def(tree, lineno)
        if node is not None and getattr(node, "end_lineno", None):
            try:
                lines = Path(file).read_text(encoding="utf-8").splitlines()  # type: ignore[arg-type]
                return "\n".join(lines[node.lineno - 1 : node.end_lineno])
            except OSError:
                pass
    return _snippet(file, lineno)


def _payload(flow: Flow, diagnostics: dict[str, list[dict]] | None = None) -> dict:
    tree_cache: dict[str, ast.Module | None] = {}
    nodes = []
    for name, node in flow.nodes.items():
        kind = "external" if node.external else node.kind
        schema = None
        if kind == "class":
            tree = _get_tree(node.file, tree_cache)
            if tree is not None and node.lineno is not None:
                schema = extract_pydantic_fields(tree, node.lineno)
        nodes.append({
            "id": name,
            "label": name.rsplit(".", 1)[-1],
            "kind": kind,
            "module": node.module,
            "parent": node.parent if node.parent in flow.nodes else None,
            "file": node.file,
            "lineno": node.lineno,
            "calls": node.calls,
            "total_time": node.total_time,
            "full_source": _full_source(node.file, node.lineno, tree_cache),
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
    """
    payload = _payload(flow, diagnostics)
    payload["serve"] = serve
    payload["serve_token"] = serve_token
    payload_json = json.dumps(payload).replace("</", "<\\/")
    vendor_scripts = "\n".join(
        f"<script>\n{_read_vendor(name)}\n</script>" for name in _VENDOR_FILES
    )
    title = f"agentx flow — {flow.entry or flow.scope}"
    html = _HTML_TEMPLATE
    html = html.replace("__TITLE__", title)
    html = html.replace("__VENDOR_SCRIPTS__", vendor_scripts)
    html = html.replace("__CSS__", _CSS)
    # __APP_JS__ itself contains the __GRAPH_DATA__ placeholder, so it must be
    # substituted in before the graph JSON is filled in below.
    html = html.replace("__APP_JS__", _APP_JS)
    html = html.replace("__GRAPH_DATA__", payload_json)
    return html


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
.log-stdout { color: #d8d8d8; }
.log-stderr { color: #ff8080; }
.log-trace { color: #7ec8e3; }
.log-info { color: #999; font-style: italic; }
"""

_APP_JS = """
(function () {
  const DATA = __GRAPH_DATA__;
  const COLORS = DATA.colors;

  cytoscape.use(cytoscapeDagre);

  const root = document.documentElement;
  const savedTheme = localStorage.getItem('agentx-flow-theme');
  if (savedTheme) root.className = savedTheme;

  document.getElementById('themeToggle').addEventListener('click', () => {
    root.className = root.className === 'dark' ? 'light' : 'dark';
    localStorage.setItem('agentx-flow-theme', root.className);
  });

  if (!DATA.nodes.length) {
    document.getElementById('main').innerHTML = '<div id="empty">(no functions found)</div>';
    return;
  }

  const byId = {};
  for (const n of DATA.nodes) byId[n.id] = n;

  // Level-of-detail: which kinds are visible at each level, coarsest first.
  const LEVEL_KINDS = {
    modules: new Set(['module', 'package']),
    classes: new Set(['module', 'package', 'class']),
    full: new Set(['module', 'package', 'class', 'function']),
  };
  // Legend on/off state, baked into the visible set (not a post-hoc CSS hide)
  // so hidden kinds don't still skew the layout of what IS shown.
  const kindFilters = {
    function: true, class: true, module: true, package: true,
    external: DATA.scope !== 'project',
  };
  function isVisibleAt(node, level) {
    if (!kindFilters[node.kind]) return false;
    return node.kind === 'external' || LEVEL_KINDS[level].has(node.kind);
  }
  // Climb a node's `parent` chain to the nearest ancestor visible at `level`
  // (itself, if already visible) — this is how a fine-grained call edge
  // becomes a coarse module-to-module edge in the collapsed views.
  function nearestVisible(nodeId, level) {
    let cur = byId[nodeId];
    while (cur && !isVisibleAt(cur, level)) {
      cur = cur.parent ? byId[cur.parent] : null;
    }
    return cur ? cur.id : null;
  }
  function buildElementsForLevel(level) {
    const visibleIds = new Set(DATA.nodes.filter(n => isVisibleAt(n, level)).map(n => n.id));
    const nodeEls = [];
    for (const id of visibleIds) {
      const n = byId[id];
      const d = { id: n.id, label: n.label, kind: n.kind, calls: n.calls, errCount: (n.type_errors || []).length };
      let p = n.parent;
      while (p && !visibleIds.has(p)) p = byId[p] ? byId[p].parent : null;
      if (p) d.parent = p;
      nodeEls.push({ data: d });
    }
    const counts = new Map();
    for (const e of DATA.edges) {
      const s = nearestVisible(e.source, level);
      const t = nearestVisible(e.target, level);
      if (!s || !t || s === t) continue;
      const key = s + ' ' + t;
      counts.set(key, (counts.get(key) || 0) + 1);
    }
    const edgeEls = [];
    let i = 0;
    for (const [key, count] of counts) {
      const [s, t] = key.split(' ');
      edgeEls.push({ data: { id: 'e' + (i++), source: s, target: t, count } });
    }
    return { nodeEls, edgeEls };
  }

  const cy = cytoscape({
    container: document.getElementById('cy'),
    elements: [],
    style: [
      { selector: 'node', style: {
        'background-color': ele => COLORS[ele.data('kind')] || COLORS.function,
        'label': 'data(label)', 'font-size': 10, color: '#fff',
        'text-valign': 'center', 'text-halign': 'center',
        width: 'label', height: 22, padding: '6px', shape: 'round-rectangle',
        'text-wrap': 'none',
      } },
      { selector: 'node[kind = "external"]', style: {
        'border-width': 2, 'border-style': 'dashed', 'border-color': '#777', color: '#222',
      } },
      { selector: 'node[errCount > 0]', style: {
        'border-width': 3, 'border-style': 'solid', 'border-color': '#EE6677',
      } },
      { selector: '$node > node', style: {
        'background-opacity': 0.12, 'border-width': 1, 'border-color': '#66CCEE',
        'border-style': 'solid', label: 'data(label)', 'text-valign': 'top',
        'text-halign': 'center', 'font-size': 11, 'font-weight': 600, padding: '14px',
      } },
      { selector: 'edge', style: {
        width: 1.4, 'line-color': '#9aa', 'target-arrow-color': '#9aa',
        'target-arrow-shape': 'triangle', 'curve-style': 'bezier', 'arrow-scale': 0.8,
      } },
      { selector: '.eh-highlight, .path-highlight', style: {
        'line-color': '#EE6677', 'target-arrow-color': '#EE6677',
        'background-color': '#EE6677', 'z-index': 999,
      } },
      { selector: '.faded', style: { opacity: 0.15 } },
      { selector: 'node.running', style: { 'overlay-color': '#F0C808', 'overlay-opacity': 0.45, 'overlay-padding': 6 } },
      { selector: 'node.done-ok', style: { 'overlay-color': '#2ca02c', 'overlay-opacity': 0.3, 'overlay-padding': 6 } },
    ],
    layout: { name: 'dagre', rankDir: 'TB', nodeSep: 30, rankSep: 55, animate: false },
    wheelSensitivity: 0.25,
  });

  function fitVisible() {
    const visible = cy.nodes(':visible');
    if (visible.length) cy.fit(visible, 40);
  }

  let currentLevel = null;
  let adjacency = {};
  function rebuildAdjacency(edgeEls) {
    adjacency = {};
    for (const el of edgeEls) {
      const { source, target } = el.data;
      (adjacency[source] ||= []).push(target);
    }
  }
  function setDetail(level) {
    currentLevel = level;
    const { nodeEls, edgeEls } = buildElementsForLevel(level);
    cy.elements().remove();
    cy.add(nodeEls.concat(edgeEls));
    cy.layout({ name: 'dagre', rankDir: 'TB', nodeSep: 30, rankSep: 55, animate: false }).run();
    rebuildAdjacency(edgeEls);
    document.querySelectorAll('#detailSeg .btn').forEach(b => b.classList.toggle('active', b.dataset.level === level));
    fitVisible();
  }
  document.querySelectorAll('#detailSeg .btn').forEach(b => {
    b.addEventListener('click', () => setDetail(b.dataset.level));
  });

  // Legend: toggle a kind in/out of the graph entirely (not just CSS display,
  // so a hidden kind doesn't still skew the layout of what remains visible).
  document.querySelectorAll('.legend .chip').forEach(chip => {
    chip.addEventListener('click', () => {
      chip.classList.toggle('off');
      kindFilters[chip.dataset.kind] = !chip.classList.contains('off');
      setDetail(currentLevel);
    });
  });
  if (!kindFilters.external) {
    document.querySelector('.legend .chip[data-kind="external"]').classList.add('off');
  }

  const LARGE = DATA.nodes.length > 80;
  if (DATA.scope === 'project') {
    setDetail(LARGE ? 'modules' : 'full');
  } else {
    setDetail('full');
    document.getElementById('detailSeg').style.display = 'none';
  }

  // Search.
  const searchBox = document.getElementById('search');
  searchBox.addEventListener('input', () => {
    const q = searchBox.value.trim().toLowerCase();
    cy.elements().removeClass('faded');
    if (!q) return;
    const matches = cy.nodes().filter(n => n.data('id').toLowerCase().includes(q));
    cy.elements().difference(matches).addClass('faded');
    if (matches.length) cy.animate({ fit: { eles: matches, padding: 40 } }, { duration: 200 });
  });

  // Click node -> side panel.
  const panel = document.getElementById('panel');
  const esc = s => String(s).replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
  function showPanel(n) {
    const d = DATA.nodes.find(x => x.id === n.data('id'));
    if (!d) return;
    let meta = d.kind;
    if (d.file) meta += ` · ${d.file}${d.lineno ? ':' + d.lineno : ''}`;
    if (d.calls) meta += ` · ${d.calls} call${d.calls === 1 ? '' : 's'}, ${(d.total_time * 1000).toFixed(1)}ms`;
    let html = `<h2>${d.id}</h2><div class="meta">${meta}</div>`;
    if (d.signature) html += `<div class="sig"><code>${esc(d.signature)}</code></div>`;
    if (d.type_errors && d.type_errors.length) {
      html += `<div class="section-title">Type errors (${d.type_errors.length})</div>` +
        `<ul class="diag-list">` +
        d.type_errors.map(e => `<li class="diag-${esc(e.severity)}">line ${e.line}: ${esc(e.message)}</li>`).join('') +
        `</ul>`;
    }
    if (d.schema) {
      html += `<div class="section-title">Fields</div><table class="schema-table"><tr><th>name</th><th>type</th><th>default</th><th>req</th></tr>` +
        d.schema.map(f => `<tr><td>${esc(f.name)}</td><td>${esc(f.type)}</td><td>${f.default !== null ? esc(f.default) : '—'}</td><td>${f.required ? 'yes' : ''}</td></tr>`).join('') +
        `</table>`;
    }
    if (d.full_source) html += `<div class="section-title">Source</div><pre>${esc(d.full_source)}</pre>`;
    html += `<p class="hint">Click a second node to highlight the call path between them.</p>`;
    panel.innerHTML = html;
  }
  panel.innerHTML = '<p class="hint">Click a node to inspect it. Click two nodes to highlight the path between them.</p>';

  // Two-click path highlight (directed BFS over the *current level's* edges,
  // kept up to date by rebuildAdjacency() every time the detail level changes).
  let picked = [];
  function shortestPath(a, b) {
    const seen = new Set([a]); const prev = {}; const queue = [a];
    while (queue.length) {
      const cur = queue.shift();
      if (cur === b) break;
      for (const nxt of (adjacency[cur] || [])) {
        if (!seen.has(nxt)) { seen.add(nxt); prev[nxt] = cur; queue.push(nxt); }
      }
    }
    if (!seen.has(b)) return null;
    const path = [b];
    while (path[path.length - 1] !== a) path.push(prev[path[path.length - 1]]);
    return path.reverse();
  }
  cy.on('tap', 'node', evt => {
    const n = evt.target;
    showPanel(n);
    picked.push(n.data('id'));
    if (picked.length === 2) {
      cy.elements().removeClass('path-highlight');
      const path = shortestPath(picked[0], picked[1]) || shortestPath(picked[1], picked[0]);
      if (path) {
        for (let i = 0; i < path.length; i++) {
          cy.getElementById(path[i]).addClass('path-highlight');
          if (i > 0) cy.edges(`[source = "${path[i-1]}"][target = "${path[i]}"]`).addClass('path-highlight');
        }
      }
      picked = [];
    } else if (picked.length > 2) {
      picked = [n.data('id')];
    }
  });

  // 2D / 3D toggle.
  let graph3d = null;
  const cyEl = document.getElementById('cy');
  const g3dEl = document.getElementById('graph3d');
  document.getElementById('view2d').addEventListener('click', () => {
    document.getElementById('view2d').classList.add('active');
    document.getElementById('view3d').classList.remove('active');
    g3dEl.style.display = 'none'; cyEl.style.display = 'block';
    cy.resize();
  });
  document.getElementById('view3d').addEventListener('click', () => {
    document.getElementById('view3d').classList.add('active');
    document.getElementById('view2d').classList.remove('active');
    cyEl.style.display = 'none'; g3dEl.style.display = 'block';
    if (!graph3d) {
      graph3d = ForceGraph3D()(g3dEl)
        .graphData({
          nodes: DATA.nodes.map(n => ({ id: n.id, name: n.id, kind: n.kind })),
          links: DATA.edges.map(e => ({ source: e.source, target: e.target })),
        })
        .nodeLabel('name')
        .nodeColor(n => COLORS[n.kind] || COLORS.function)
        .linkDirectionalArrowLength(3.5)
        .linkColor(() => '#9aa')
        .dagMode('td')
        .dagLevelDistance(90)
        .backgroundColor('rgba(0,0,0,0)');
    }
    graph3d.width(g3dEl.clientWidth).height(g3dEl.clientHeight);
  });

  // Live execution (--serve only) — Run/Stop + streamed logs + node pulses.
  const runBtn = document.getElementById('runBtn');
  const stopBtn = document.getElementById('stopBtn');
  if (DATA.serve) {
    runBtn.style.display = '';
    const logPane = document.getElementById('logPane');
    const logBody = document.getElementById('logBody');
    const token = DATA.serve_token;
    let currentRunId = null;

    function logLine(cls, text) {
      const el = document.createElement('div');
      el.className = 'log-line ' + cls;
      el.textContent = text;
      logBody.appendChild(el);
      logBody.scrollTop = logBody.scrollHeight;
    }
    function markNode(nodeId, cls) {
      const ele = cy.getElementById(nodeId);
      if (ele && ele.length) { ele.removeClass('running done-ok'); ele.addClass(cls); }
    }

    runBtn.addEventListener('click', async () => {
      logPane.style.display = 'flex';
      logBody.innerHTML = '';
      cy.nodes().removeClass('running done-ok');
      runBtn.style.display = 'none';
      stopBtn.style.display = '';
      logLine('log-info', 'Starting run...');
      const res = await fetch(`/api/run?token=${token}`, { method: 'POST' });
      const { run_id } = await res.json();
      currentRunId = run_id;
      const evtSource = new EventSource(`/api/stream/${run_id}?token=${token}`);
      evtSource.onmessage = (e) => {
        const ev = JSON.parse(e.data);
        if (ev.type === 'stdout') logLine('log-stdout', ev.text);
        else if (ev.type === 'stderr') logLine('log-stderr', ev.text);
        else if (ev.type === 'trace_call') { logLine('log-trace', '→ ' + ev.node); markNode(ev.node, 'running'); }
        else if (ev.type === 'trace_return') { logLine('log-trace', '← ' + ev.node + ` (${ev.elapsed_ms.toFixed(1)}ms)`); markNode(ev.node, 'done-ok'); }
        else if (ev.type === 'error') logLine('log-stderr', 'ERROR: ' + ev.message);
        else if (ev.type === 'done') {
          logLine('log-info', `Process exited (code ${ev.exit_code}).`);
          runBtn.style.display = ''; stopBtn.style.display = 'none';
          evtSource.close();
        }
      };
    });
    stopBtn.addEventListener('click', async () => {
      if (currentRunId) await fetch(`/api/stop/${currentRunId}?token=${token}`, { method: 'POST' });
    });
    document.getElementById('closeLog').addEventListener('click', () => { logPane.style.display = 'none'; });
  } else {
    runBtn.style.display = 'none';
    stopBtn.style.display = 'none';
  }
})();
"""

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>__CSS__</style>
</head>
<body>
<div id="app">
  <header>
    <h1>__TITLE__</h1>
    <input type="text" id="search" placeholder="Search nodes...">
    <div class="legend">
      <span class="chip" data-kind="function"><span class="swatch" style="background:#4477AA"></span>function</span>
      <span class="chip" data-kind="class"><span class="swatch" style="background:#CCBB44"></span>class</span>
      <span class="chip" data-kind="module"><span class="swatch" style="background:#66CCEE"></span>module</span>
      <span class="chip" data-kind="external"><span class="swatch" style="background:#999"></span>external</span>
    </div>
    <div class="seg" id="detailSeg">
      <button class="btn" data-level="modules">Modules</button>
      <button class="btn" data-level="classes">Classes</button>
      <button class="btn" data-level="full">Full</button>
    </div>
    <div class="seg">
      <button class="btn active" id="view2d">2D</button>
      <button class="btn" id="view3d">3D (experimental)</button>
    </div>
    <button class="btn" id="themeToggle">Toggle theme</button>
    <button class="btn run" id="runBtn" style="display:none" title="Executes this file on your machine">▶ Run (executes code)</button>
    <button class="btn stop" id="stopBtn" style="display:none">■ Stop</button>
  </header>
  <main id="main">
    <div id="cy"></div>
    <div id="graph3d" style="display:none"></div>
    <aside id="panel"></aside>
  </main>
  <div id="logPane">
    <div class="log-header"><span>Execution log</span><button class="btn-mini" id="closeLog">×</button></div>
    <div id="logBody"></div>
  </div>
</div>
__VENDOR_SCRIPTS__
<script>__APP_JS__</script>
</body>
</html>
"""

__all__ = ["render_html"]
