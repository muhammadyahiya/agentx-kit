import { Handle, Position, type NodeProps, type Node } from "@xyflow/react";
import type { GitInfo, NodeKind } from "../../types";

export type KindNodeData = {
  label: string;
  kind: NodeKind;
  calls: number;
  totalTime: number;
  errCount: number;
  git: GitInfo | null;
  hasChildren: boolean;
  color: string;
  maxCalls?: number;
  status?: "running" | "done";
};

// Same buckets/colors as the vanilla viewer's recency overlay (app.js) — a
// git-blame-derived "how recently did this change" heat, warm = recent.
const RECENCY_BUCKETS: { maxDays: number; color: string }[] = [
  { maxDays: 2, color: "#D7263D" },
  { maxDays: 14, color: "#F46036" },
  { maxDays: 60, color: "#F9C74F" },
  { maxDays: 365, color: "#90BE6D" },
];

function recencyColor(git: GitInfo | null): string | null {
  if (!git) return null;
  const ageDays = (Date.now() / 1000 - git.last_change) / 86400;
  for (const { maxDays, color } of RECENCY_BUCKETS) {
    if (ageDays <= maxDays) return color;
  }
  return null;
}

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
  const recency = recencyColor(data.git);
  return (
    <div
      className={`rf-kind-node kind-${data.kind}${selected ? " is-selected" : ""}${
        data.errCount > 0 ? " has-error" : ""
      }${data.status ? ` status-${data.status}` : ""}`}
      style={{ borderColor: data.color }}
    >
      <Handle type="target" position={Position.Top} />
      {recency && (
        <span
          className="rf-recency-dot"
          style={{ background: recency }}
          title={`Recently changed (git blame) — ${new Date(data.git!.last_change * 1000).toLocaleDateString()}, ${data.git!.churn} commit${data.git!.churn === 1 ? "" : "s"} touching this range`}
        />
      )}
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
