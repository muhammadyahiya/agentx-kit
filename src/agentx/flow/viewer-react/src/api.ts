// Thin wrappers around the exact HTTP contract `agentx.flow.server.build_app`
// exposes (../../server.py) — same routes/shapes the vanilla viewer's app.js
// uses, so this prototype can be pointed at a real `agentx flow --serve`
// backend by running `vite dev` behind its proxy, or once vendored, served
// from the same origin (see README.md).

export interface SaveRequest {
  file: string;
  lineno: number;
  end_lineno: number;
  source: string;
}

export async function saveNodeSource(token: string, req: SaveRequest): Promise<void> {
  const res = await fetch(`/api/save?token=${encodeURIComponent(token)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || res.statusText);
  }
}

export async function startRun(token: string, command: string | null): Promise<{ run_id: string }> {
  const res = await fetch(`/api/run?token=${encodeURIComponent(token)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ command: command || "" }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

export async function stopRun(token: string, runId: string): Promise<void> {
  await fetch(`/api/stop/${runId}?token=${encodeURIComponent(token)}`, { method: "POST" });
}

export function streamUrl(token: string, runId: string): string {
  return `/api/stream/${runId}?token=${encodeURIComponent(token)}`;
}
