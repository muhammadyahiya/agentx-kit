import { type NodeProps, type Node } from "@xyflow/react";
import type { NodeKind } from "../../types";

export type GroupNodeData = {
  label: string;
  kind: NodeKind;
  calls: number;
  totalTime: number;
  errCount: number;
  hasChildren: boolean;
  color: string;
  collapsed?: boolean;
  onToggleCollapse?: (id: string) => void;
};

export type GroupNode = Node<GroupNodeData, "group">;

/** Compound/cluster node for a module, package, or class that currently has
 * visible children — a real React Flow group node (`parentId`+`extent:
 * 'parent'` on its children, see layout/elk.ts) instead of Cytoscape's
 * `$node > node` compound-node style selector. The header includes a
 * collapse toggle independent of the global Modules/Classes/Full LOD
 * control (see graph/visibility.ts's `collapsedIds`). */
export default function GroupNode({ id, data }: NodeProps<GroupNode>) {
  return (
    <div className={`rf-group-node kind-${data.kind}`} style={{ borderColor: data.color }}>
      <div className="rf-group-node__header" style={{ background: `${data.color}26`, borderColor: data.color }}>
        <button
          className="rf-group-node__collapse"
          title="Collapse/expand this group"
          onClick={(e) => {
            e.stopPropagation();
            data.onToggleCollapse?.(id);
          }}
        >
          {data.collapsed ? "▸" : "▾"}
        </button>
        <span className="rf-group-node__label" title={data.label}>
          {data.label}
        </span>
        {data.errCount > 0 && <span className="rf-badge rf-badge--error">{data.errCount}</span>}
      </div>
    </div>
  );
}
