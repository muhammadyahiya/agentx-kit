# agentx flow — React Flow v12 viewer (experimental)

Source for the `agentx flow --ui --react` viewer: React 18 + [`@xyflow/react`](https://reactflow.dev/)
(React Flow v12) + `elkjs` (layered layout) + `@monaco-editor/react` (side-panel edit-in-place).
Same `nodes`/`edges` payload contract as the default Cytoscape viewer
(`../viewer/app.js`, `../htmlgen.py`) and the same `/api/save`, `/api/run`,
`/api/stream/<run_id>`, `/api/stop/<run_id>` HTTP contract as `../server.py`
for `--serve` mode.

This directory is **build source only** — it is excluded from the published
wheel (see `pyproject.toml`'s `[tool.hatch.build.targets.wheel]`). What ships
at runtime is a single prebuilt artifact: `../viewer/react-viewer.html`.

## Rebuilding the vendored bundle

```bash
cd src/agentx/flow/viewer-react
npm install
npm run build            # tsc -b && vite build -> dist/index.html (single file)
cp dist/index.html ../viewer/react-viewer.html
```

`vite.config.ts` uses `vite-plugin-singlefile` with `cssCodeSplit: false` and
a large `assetsInlineLimit` so the whole build — JS, CSS, and any small
assets — collapses into one `dist/index.html`, the same "one self-contained
file" shape as the default viewer. `htmlgen._read_react_bundle()` reads that
file, swaps in the real `<title>`, and injects
`<script>window.AGENTX_FLOW_DATA = {...}</script>` right after `<head>` —
`src/data.ts` already prefers that global over its dev-mode mock JSON fetch,
so no other wiring is needed.

## Local dev / preview without agentx

```bash
npm run dev   # serves public/mock-data.json (generated from a real agentx.flow.htmlgen._payload())
```

## Status

Verified working end-to-end in a browser against a real generated payload:
ELK layered layout, custom per-kind node components with call/error badges,
compound/group nodes (module → class → function, collapsible, re-runs ELK
layout), built-in minimap + controls, click-node side panel, two-click
shortest-path highlighting, search-to-fade, dark/light theme toggle.

Implemented against the exact `server.py` contract but only curl-verified
(not yet clicked through the live UI against a running `--serve` backend):
Monaco edit-in-place, and the Run/Stop/SSE live-execution log panel. Treat
`--react --serve` as more experimental than `--react` alone until someone
exercises those two paths by hand.
