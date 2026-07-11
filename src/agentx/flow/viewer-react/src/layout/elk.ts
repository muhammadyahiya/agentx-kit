import ELK, { type ElkNode } from "elkjs/lib/elk.bundled.js";
import type { Node as RFNode, Edge as RFEdge } from "@xyflow/react";
import type { FlowNodeData, NodeKind } from "../types";
import type { VisibleGraph } from "../graph/visibility";

const elk = new ELK();

// Leaf (non-container) node box size — sized to fit label + badge row.
const LEAF_W = 190;
const LEAF_H = 56;
// A manually-collapsed group (see graph/visibility.ts's `collapsedIds`) still
// renders as a (small, childless) GroupNode rather than falling back to a
// plain KindNode, so its expand affordance stays visible.
const COLLAPSED_GROUP_W = 170;
const COLLAPSED_GROUP_H = 44;

// Matches the current viewer's dagre config (`rankDir: 'TB', nodeSep: 30,
// rankSep: 55` in ../../viewer/app.js) as closely as ELK's option names allow.
const ROOT_LAYOUT_OPTIONS: Record<string, string> = {
  "elk.algorithm": "layered",
  "elk.direction": "DOWN",
  "elk.hierarchyHandling": "INCLUDE_CHILDREN",
  "elk.spacing.nodeNode": "30",
  "elk.layered.spacing.nodeNodeBetweenLayers": "55",
  "elk.layered.crossingMinimization.strategy": "LAYER_SWEEP",
  "elk.layered.nodePlacement.strategy": "BRANDES_KOEPF",
  "elk.edgeRouting": "ORTHOGONAL",
};

// Group/compound (module or class) container options — extra top padding
// reserves room for the header label rendered by GroupNode.tsx.
const CONTAINER_LAYOUT_OPTIONS: Record<string, string> = {
  "elk.padding": "[top=40,left=14,bottom=14,right=14]",
  "elk.spacing.nodeNode": "24",
  "elk.layered.spacing.nodeNodeBetweenLayers": "36",
};

export interface LayoutResult {
  nodes: RFNode[];
  edges: RFEdge[];
}

/** Run ELK's layered layout over the currently-visible subset of the graph
 * (see graph/visibility.ts) and turn the result into React Flow nodes/edges.
 *
 * Compound (module -> class -> function) nesting is expressed to ELK as
 * nested `children` arrays with `elk.hierarchyHandling: INCLUDE_CHILDREN`,
 * which lets a single flat `edges` list at the root reference node ids at
 * any depth — ELK works out cross-hierarchy routing itself. Conveniently,
 * ELK reports each child's x/y *relative to its parent container*, which is
 * exactly the coordinate space React Flow expects for a node with
 * `parentId`+`extent: 'parent'` — no coordinate-flattening pass needed.
 */
export async function layoutGraph(
  visible: VisibleGraph,
  byId: Record<string, FlowNodeData>,
  collapsedIds: ReadonlySet<string> = new Set(),
): Promise<LayoutResult> {
  const childrenOf = new Map<string, string[]>();
  for (const n of visible.nodes) {
    if (n.parent) {
      const list = childrenOf.get(n.parent) ?? [];
      list.push(n.id);
      childrenOf.set(n.parent, list);
    }
  }
  const roots = visible.nodes.filter((n) => !n.parent).map((n) => n.id);

  function buildElkNode(id: string): ElkNode {
    const kids = childrenOf.get(id) ?? [];
    if (kids.length === 0) {
      const collapsed = collapsedIds.has(id);
      return { id, width: collapsed ? COLLAPSED_GROUP_W : LEAF_W, height: collapsed ? COLLAPSED_GROUP_H : LEAF_H };
    }
    return {
      id,
      layoutOptions: CONTAINER_LAYOUT_OPTIONS,
      children: kids.map(buildElkNode),
    };
  }

  const elkRoot: ElkNode = {
    id: "__root__",
    layoutOptions: ROOT_LAYOUT_OPTIONS,
    children: roots.map(buildElkNode),
    edges: visible.edges.map((e) => ({
      id: e.id,
      sources: [e.source],
      targets: [e.target],
    })),
  };

  const result = await elk.layout(elkRoot);

  const rfNodes: RFNode[] = [];
  function walk(elkNode: ElkNode, parentId?: string) {
    for (const child of elkNode.children ?? []) {
      const kids = child.children ?? [];
      const flowNode = byId[child.id];
      const hasChildren = kids.length > 0;
      const isCollapsedGroup = !hasChildren && collapsedIds.has(child.id);
      rfNodes.push({
        id: child.id,
        type: hasChildren || isCollapsedGroup ? "group" : "kind",
        position: { x: child.x ?? 0, y: child.y ?? 0 },
        ...(parentId ? { parentId, extent: "parent" as const } : {}),
        ...(hasChildren
          ? { style: { width: child.width ?? 0, height: child.height ?? 0 } }
          : {})
        ,
        data: {
          label: flowNode?.label ?? child.id,
          kind: (flowNode?.kind ?? "function") as NodeKind,
          calls: flowNode?.calls ?? 0,
          totalTime: flowNode?.total_time ?? 0,
          errCount: flowNode?.type_errors?.length ?? 0,
          git: flowNode?.git ?? null,
          hasChildren,
          collapsed: isCollapsedGroup,
        },
        draggable: true,
      });
      if (hasChildren) walk(child, child.id);
    }
  }
  walk(result);

  const rfEdges: RFEdge[] = visible.edges.map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    label: e.count > 1 ? String(e.count) : undefined,
    type: "smoothstep",
    data: { count: e.count },
  }));

  return { nodes: rfNodes, edges: rfEdges };
}
