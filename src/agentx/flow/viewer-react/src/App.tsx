import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  type NodeMouseHandler,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import "./App.css";

import { loadFlowData } from "./data";
import type { DetailLevel, FlowPayload, NodeKind } from "./types";
import { computeVisibleGraph, shortestPath } from "./graph/visibility";
import { layoutGraph } from "./layout/elk";
import KindNode from "./components/nodes/KindNode";
import GroupNode from "./components/nodes/GroupNode";
import SidePanel from "./components/SidePanel";
import Header from "./components/Header";
import LogPane from "./components/LogPane";
import { useLiveExec } from "./hooks/useLiveExec";

const nodeTypes = { kind: KindNode, group: GroupNode };

export default function App() {
  const [payload, setPayload] = useState<FlowPayload | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [level, setLevel] = useState<DetailLevel>("full");
  const [kindFilters, setKindFilters] = useState<Record<NodeKind, boolean>>({
    function: true,
    class: true,
    module: true,
    package: true,
    external: true,
  });
  const [collapsedIds, setCollapsedIds] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState("");
  const [darkMode, setDarkMode] = useState(
    () => localStorage.getItem("agentx-flow-react-theme") === "dark",
  );
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const pickedRef = useRef<string[]>([]);
  const [pathIds, setPathIds] = useState<Set<string>>(new Set());
  const [edited, setEdited] = useState<Set<string>>(new Set());
  const [logPaneOpen, setLogPaneOpen] = useState(false);

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const adjacencyRef = useRef<Record<string, string[]>>({});
  const layoutTokenRef = useRef(0);

  const byId = useMemo(() => {
    const m: Record<string, FlowPayload["nodes"][number]> = {};
    if (payload) for (const n of payload.nodes) m[n.id] = n;
    return m;
  }, [payload]);

  const serveToken = payload?.serve_token ?? null;
  const canEdit = !!payload?.serve;
  const liveExec = useLiveExec(serveToken);

  useEffect(() => {
    document.documentElement.className = darkMode ? "dark" : "light";
    localStorage.setItem("agentx-flow-react-theme", darkMode ? "dark" : "light");
  }, [darkMode]);

  useEffect(() => {
    loadFlowData()
      .then((data) => {
        setPayload(data);
        // Same default as app.js: default to "modules" for a large project
        // graph, "full" (and hide the toggle) for a single-file graph.
        const large = data.nodes.length > 80;
        setLevel(data.scope === "project" ? (large ? "modules" : "full") : "full");
        setKindFilters((prev) => ({ ...prev, external: data.scope !== "project" }));
      })
      .catch((e) => setLoadError(String(e)));
  }, []);

  // Re-run ELK layout whenever the *visible* subset of the graph changes —
  // level-of-detail, legend filters, or manual group collapse/expand.
  useEffect(() => {
    if (!payload) return;
    const token = ++layoutTokenRef.current;
    const visible = computeVisibleGraph(payload, level, kindFilters, collapsedIds);
    adjacencyRef.current = visible.adjacency;
    const maxCalls = Math.max(1, ...payload.nodes.map((n) => n.calls));
    layoutGraph(visible, byId, collapsedIds).then(({ nodes: rfNodes, edges: rfEdges }) => {
      if (token !== layoutTokenRef.current) return; // a newer layout superseded this one
      const enriched = rfNodes.map((n) => ({
        ...n,
        data: {
          ...n.data,
          color: payload.colors[(n.data as { kind: NodeKind }).kind] ?? "#4477AA",
          maxCalls,
          onToggleCollapse: (id: string) =>
            setCollapsedIds((prev) => {
              const next = new Set(prev);
              if (next.has(id)) next.delete(id);
              else next.add(id);
              return next;
            }),
        },
      }));
      setNodes(enriched);
      setEdges(rfEdges);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [payload, level, kindFilters, collapsedIds, byId]);

  // Search: fade non-matching nodes (same behavior as app.js's #search input).
  useEffect(() => {
    const q = search.trim().toLowerCase();
    setNodes((prev) =>
      prev.map((n) => ({
        ...n,
        className: q && !n.id.toLowerCase().includes(q) ? "rf-faded" : undefined,
      })),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  // Live-exec node status pulses (running/done), from useLiveExec's SSE handler.
  useEffect(() => {
    if (Object.keys(liveExec.nodeStatus).length === 0) return;
    setNodes((prev) =>
      prev.map((n) =>
        liveExec.nodeStatus[n.id]
          ? { ...n, data: { ...n.data, status: liveExec.nodeStatus[n.id] } }
          : n,
      ),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [liveExec.nodeStatus]);

  // Path-highlight styling: mark nodes/edges on the last computed path.
  useEffect(() => {
    setNodes((prev) => prev.map((n) => ({ ...n, selected: pathIds.has(n.id) })));
    setEdges((prev) =>
      prev.map((e) => ({
        ...e,
        style:
          pathIds.has(e.source) && pathIds.has(e.target) && e.source !== e.target
            ? { stroke: "#EE6677", strokeWidth: 2.5 }
            : undefined,
        animated: pathIds.has(e.source) && pathIds.has(e.target),
      })),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathIds]);

  const onNodeClick: NodeMouseHandler = useCallback((_evt, node) => {
    setSelectedId(node.id);
    const prev = pickedRef.current;
    const next = prev.length >= 2 ? [node.id] : [...prev, node.id];
    pickedRef.current = next;
    if (next.length === 2) {
      const path =
        shortestPath(adjacencyRef.current, next[0], next[1]) ??
        shortestPath(adjacencyRef.current, next[1], next[0]);
      setPathIds(new Set(path ?? []));
    } else {
      setPathIds(new Set());
    }
  }, []);

  function toggleKind(k: NodeKind) {
    setKindFilters((prev) => ({ ...prev, [k]: !prev[k] }));
  }

  function handleSaved(id: string, newSource: string) {
    if (payload) {
      const n = payload.nodes.find((x) => x.id === id);
      if (n) n.full_source = newSource;
    }
    setEdited((prev) => new Set(prev).add(id));
  }

  async function handleRun() {
    setLogPaneOpen(true);
    await liveExec.run(null);
  }
  async function handleRunCommand(cmd: string) {
    setLogPaneOpen(true);
    await liveExec.run(cmd);
  }

  if (loadError) {
    return <div id="empty">Failed to load graph data: {loadError}</div>;
  }
  if (!payload) {
    return <div id="empty">Loading...</div>;
  }
  if (!payload.nodes.length) {
    return <div id="empty">(no functions found)</div>;
  }

  const selectedNode = selectedId ? byId[selectedId] ?? null : null;
  const title = `agentx flow — ${payload.entry ?? payload.scope} (React)`;

  return (
    <div id="app">
      <Header
        title={title}
        search={search}
        onSearch={setSearch}
        level={level}
        onLevel={setLevel}
        showLevelToggle={payload.scope === "project"}
        kindFilters={kindFilters}
        onToggleKind={toggleKind}
        colors={payload.colors}
        darkMode={darkMode}
        onToggleTheme={() => setDarkMode((d) => !d)}
        serve={!!payload.serve}
        running={liveExec.running}
        onRun={handleRun}
        onStop={liveExec.stop}
      />
      <main id="main">
        <div id="canvas">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeClick={onNodeClick}
            fitView
            minZoom={0.05}
            proOptions={{ hideAttribution: true }}
          >
            <Background />
            <Controls />
            <MiniMap
              nodeColor={(n) => (n.data as { color?: string })?.color ?? "#999"}
              pannable
              zoomable
            />
          </ReactFlow>
        </div>
        <SidePanel
          node={selectedNode}
          canEdit={canEdit}
          serveToken={serveToken}
          edited={edited}
          onSaved={handleSaved}
          darkMode={darkMode}
        />
      </main>
      <LogPane
        visible={logPaneOpen}
        log={liveExec.log}
        running={liveExec.running}
        onClose={() => setLogPaneOpen(false)}
        onRunCommand={handleRunCommand}
      />
    </div>
  );
}
