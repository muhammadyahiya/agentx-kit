import { Handle, Position, type NodeProps, type Node } from "@xyflow/react";
import type { NodeKind } from "../../types";

export type KindNodeData = {
  label: string;
  kind: NodeKind;
  calls: number;
  totalTime: number;
  errCount: number;
  hasChildren: boolean;
  color: string;
  maxCalls?: number;
  status?: "running" | "done";
};

export type KindNode = Node<KindNodeData, "kind">;

const KIND_ICON: Record<NodeKind, string> = {
  function: "ƒ", // ƒ
  class: "C",
  module: "M",
  package: "P",
  external: "↯", // ↯-ish external glyph
};

/** Leaf node (function / external, or a childless module|class|package at the
 * current LOD/collapse state). Custom React component so we get badges +
 * icons + a proportional "activity bar" (see README for why this isn't a
 * true sparkline — the data model only carries an aggregate `total_time`,
 * not a time series) instead of Cytoscape's flat style-object nodes. */
export default function KindNode({ data, selected }: NodeProps<KindNode>) {
  const barPct = data.maxCalls ? Math.min(100, (data.calls / data.maxCalls) * 100) : 0;
  return (
    <div
      className={`rf-kind-node kind-${data.kind}${selected ? " is-selected" : ""}${
        data.errCount > 0 ? " has-error" : ""
      }${data.status ? ` status-${data.status}` : ""}`}
      style={{ borderColor: data.color }}
    >
      <Handle type="target" position={Position.Top} />
      <div className="rf-kind-node__row">
        <span className="rf-kind-node__icon" style={{ background: data.color }}>
          {KIND_ICON[data.kind]}
        </span>
        <span className="rf-kind-node__label" title={data.label}>
          {data.label}
        </span>
        {data.errCount > 0 && <span className="rf-badge rf-badge--error">{data.errCount}</span>}
      </div>
      {data.calls > 0 && (
        <div className="rf-kind-node__meta">
          <span className="rf-badge rf-badge--calls">{data.calls}x</span>
          <span className="rf-kind-node__bar">
            <span className="rf-kind-node__bar-fill" style={{ width: `${barPct}%`, background: data.color }} />
          </span>
        </div>
      )}
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}
