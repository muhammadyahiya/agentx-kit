// Data contract shared with the Python backend — mirrors the shape built by
// `_payload()` in ../../htmlgen.py and consumed by ../../viewer/app.js. Keep
// these two in sync; this file has no runtime import from Python, it's just
// the TS mirror of that JSON contract.

export type NodeKind = "function" | "class" | "module" | "package" | "external";

export interface TypeError {
  line: number;
  severity: "error" | "warning" | "note" | string;
  message: string;
}

export interface SchemaField {
  name: string;
  type: string;
  default: string | null;
  required: boolean;
}

export interface GitInfo {
  last_change: number; // unix seconds, from `git blame` (see gitmeta.py)
  commit: string; // short hash
  churn: number; // distinct commits touching this node's line range
}

export interface FlowNodeData {
  id: string;
  label: string;
  kind: NodeKind;
  module: string | null;
  parent: string | null;
  file: string | null;
  lineno: number | null;
  end_lineno: number | null;
  calls: number;
  total_time: number;
  full_source: string;
  signature: string | null;
  schema: SchemaField[] | null;
  type_errors: TypeError[];
  git: GitInfo | null;
}

export interface FlowEdgeData {
  id: string;
  source: string;
  target: string;
  count: number;
}

export interface FlowPayload {
  scope: "file" | "project";
  kind: "static" | "runtime";
  entry: string | null;
  colors: Record<string, string>;
  nodes: FlowNodeData[];
  edges: FlowEdgeData[];
  // Present only when served by `agentx flow --serve` (server.py); absent
  // (undefined) for the static/offline mock JSON used in this prototype.
  serve?: boolean;
  serve_token?: string | null;
}

export type DetailLevel = "modules" | "classes" | "full";

// ---- Live-execution SSE event shapes (server.py /api/stream/<run_id>) ----

export type RunEvent =
  | { type: "stdout"; text: string; ts: number }
  | { type: "stderr"; text: string; ts: number }
  | { type: "trace_call"; node: string; ts?: number }
  | { type: "trace_return"; node: string; elapsed_ms: number; ts?: number }
  | { type: "error"; message: string; ts?: number }
  | { type: "done"; exit_code: number; ts: number };
