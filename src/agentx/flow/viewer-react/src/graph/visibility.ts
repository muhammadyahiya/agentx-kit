import type { DetailLevel, FlowNodeData, FlowPayload, NodeKind } from "../types";

// Level-of-detail: which kinds are visible at each level, coarsest first.
// Mirrors LEVEL_KINDS in ../../viewer/app.js exactly.
const LEVEL_KINDS: Record<DetailLevel, Set<NodeKind>> = {
  modules: new Set(["module", "package"]),
  classes: new Set(["module", "package", "class"]),
  full: new Set(["module", "package", "class", "function"]),
};

export interface VisibleGraph {
  /** Renderable node ids, each with a `parent` climbed up to the nearest
   * also-renderable ancestor (or undefined at the root). */
  nodes: { id: string; parent?: string }[];
  /** Aggregated, deduped edges between renderable nodes (self-loops from
   * collapsing dropped, counts summed like app.js's `buildElementsForLevel`). */
  edges: { id: string; source: string; target: string; count: number }[];
  /** directed adjacency over the *visible* edges — feed to shortestPath(). */
  adjacency: Record<string, string[]>;
}

/** Re-implements app.js's `buildElementsForLevel`/`nearestVisible`, plus an
 * extra manual-collapse layer on top of the Modules/Classes/Full LOD toggle:
 * a node in `collapsedIds` still renders itself, but hides its descendants
 * (their calls/edges reattribute to it), whereas a kind hidden by `level` or
 * `kindFilters` disappears entirely and calls reattribute to its nearest
 * visible ancestor — same distinction cytoscape's compound-node collapse
 * vs. this app's Modules/Classes/Full segmented control draws. */
export function computeVisibleGraph(
  payload: FlowPayload,
  level: DetailLevel,
  kindFilters: Record<NodeKind, boolean>,
  collapsedIds: ReadonlySet<string>,
): VisibleGraph {
  const byId: Record<string, FlowNodeData> = {};
  for (const n of payload.nodes) byId[n.id] = n;

  function isKindVisible(node: FlowNodeData): boolean {
    if (!kindFilters[node.kind]) return false;
    return node.kind === "external" || LEVEL_KINDS[level].has(node.kind);
  }

  // A node is hidden-by-collapse if any *strict ancestor* is collapsed
  // (collapsing a group hides its descendants, not the group itself).
  function isHiddenByCollapse(id: string): boolean {
    let cur = byId[id]?.parent ?? null;
    while (cur) {
      if (collapsedIds.has(cur)) return true;
      cur = byId[cur]?.parent ?? null;
    }
    return false;
  }

  function isRenderable(id: string): boolean {
    const n = byId[id];
    if (!n) return false;
    return isKindVisible(n) && !isHiddenByCollapse(id);
  }

  function nearestVisible(id: string): string | null {
    let cur: string | null = id;
    while (cur && !isRenderable(cur)) {
      cur = byId[cur]?.parent ?? null;
    }
    return cur;
  }

  const visibleIds = new Set(payload.nodes.map((n) => n.id).filter(isRenderable));
  const nodes: { id: string; parent?: string }[] = [];
  for (const id of visibleIds) {
    let p = byId[id].parent ?? null;
    while (p && !visibleIds.has(p)) p = byId[p]?.parent ?? null;
    nodes.push(p ? { id, parent: p } : { id });
  }

  const counts = new Map<string, number>();
  for (const e of payload.edges) {
    const s = nearestVisible(e.source);
    const t = nearestVisible(e.target);
    if (!s || !t || s === t) continue;
    const key = `${s} ${t}`;
    counts.set(key, (counts.get(key) ?? 0) + e.count);
  }
  const edges: VisibleGraph["edges"] = [];
  const adjacency: Record<string, string[]> = {};
  let i = 0;
  for (const [key, count] of counts) {
    const [s, t] = key.split(" ");
    edges.push({ id: `ve${i++}`, source: s, target: t, count });
    (adjacency[s] ??= []).push(t);
  }

  return { nodes, edges, adjacency };
}

/** Directed BFS shortest path over `adjacency` — same algorithm as app.js's
 * two-click path highlight. */
export function shortestPath(
  adjacency: Record<string, string[]>,
  a: string,
  b: string,
): string[] | null {
  const seen = new Set([a]);
  const prev: Record<string, string> = {};
  const queue = [a];
  while (queue.length) {
    const cur = queue.shift()!;
    if (cur === b) break;
    for (const next of adjacency[cur] ?? []) {
      if (!seen.has(next)) {
        seen.add(next);
        prev[next] = cur;
        queue.push(next);
      }
    }
  }
  if (!seen.has(b)) return null;
  const path = [b];
  while (path[path.length - 1] !== a) path.push(prev[path[path.length - 1]]);
  return path.reverse();
}
