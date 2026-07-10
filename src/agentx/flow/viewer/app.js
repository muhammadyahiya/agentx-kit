(function () {
  const DATA = window.AGENTX_FLOW_DATA;
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
    const termInput = document.getElementById('termInput');
    const token = DATA.serve_token;
    let currentRunId = null;
    let running = false;

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
    function setRunning(isRunning) {
      running = isRunning;
      runBtn.style.display = isRunning ? 'none' : '';
      stopBtn.style.display = isRunning ? '' : 'none';
      termInput.disabled = isRunning;
    }

    // command === null runs the target file (with full trace events, via
    // _serve_runner); a non-empty string runs that as a plain shell command
    // instead (no trace events — we don't control what it does — but the
    // same live stdout/stderr streaming, i.e. a minimal terminal).
    async function startRun(command) {
      if (running) return;
      logPane.style.display = 'flex';
      logBody.innerHTML = '';
      cy.nodes().removeClass('running done-ok');
      setRunning(true);
      logLine('log-info', command ? '$ ' + command : 'Starting run...');
      const res = await fetch(`/api/run?token=${token}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command: command || '' }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        logLine('log-stderr', 'Failed to start: ' + (err.detail || res.statusText));
        setRunning(false);
        return;
      }
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
          setRunning(false);
          evtSource.close();
        }
      };
    }

    runBtn.addEventListener('click', () => startRun(null));
    stopBtn.addEventListener('click', async () => {
      if (currentRunId) await fetch(`/api/stop/${currentRunId}?token=${token}`, { method: 'POST' });
    });
    termInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && termInput.value.trim()) {
        const cmd = termInput.value.trim();
        termInput.value = '';
        startRun(cmd);
      }
    });
    document.getElementById('closeLog').addEventListener('click', () => { logPane.style.display = 'none'; });
  } else {
    runBtn.style.display = 'none';
    stopBtn.style.display = 'none';
  }
})();
