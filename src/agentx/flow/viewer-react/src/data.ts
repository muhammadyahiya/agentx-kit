import type { FlowPayload } from "./types";

declare global {
  interface Window {
    // Set this the same way the current viewer does (see viewer.html.j2:
    // `window.AGENTX_FLOW_DATA = {{ graph_data }}`) once this prototype is
    // wired into htmlgen.py/server.py for real. Until then we fall back to
    // fetching the static mock payload committed under `public/`.
    AGENTX_FLOW_DATA?: FlowPayload;
  }
}

/** Load the graph payload: prefer an embedded `window.AGENTX_FLOW_DATA` (the
 * production contract, see htmlgen.py/server.py), else fetch the committed
 * mock JSON (`public/mock-data.json`, generated from this very repo via
 * `agentx.flow.htmlgen._payload()` — see viewer-react/README.md) so this
 * prototype can be previewed standalone with `npm run dev`. */
export async function loadFlowData(): Promise<FlowPayload> {
  if (window.AGENTX_FLOW_DATA) return window.AGENTX_FLOW_DATA;
  const res = await fetch(`${import.meta.env.BASE_URL}mock-data.json`);
  if (!res.ok) throw new Error(`Failed to load mock-data.json: ${res.status}`);
  return (await res.json()) as FlowPayload;
}
