import { Suspense, lazy, useState } from "react";
import type { FlowNodeData } from "../types";
import { saveNodeSource } from "../api";

// Lazy-loaded: Monaco is ~5MB, same reasoning htmlgen.py gives for only
// loading it in `--serve` mode — don't pay for it on first paint when the
// user hasn't clicked "Edit" (or isn't in serve mode at all).
const MonacoEditor = lazy(() => import("@monaco-editor/react"));

function formatAge(unixSeconds: number): string {
  const ageDays = Math.floor((Date.now() / 1000 - unixSeconds) / 86400);
  if (ageDays <= 0) return "today";
  if (ageDays === 1) return "1 day ago";
  if (ageDays < 60) return `${ageDays} days ago`;
  return `${Math.round(ageDays / 30)} months ago`;
}

interface Props {
  node: FlowNodeData | null;
  canEdit: boolean;
  serveToken: string | null;
  edited: Set<string>;
  onSaved: (id: string, newSource: string) => void;
  darkMode: boolean;
}

export default function SidePanel({ node, canEdit, serveToken, edited, onSaved, darkMode }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!node) {
    return (
      <aside id="panel">
        <p className="hint">Click a node to inspect it. Click two nodes to highlight the path between them.</p>
      </aside>
    );
  }

  let meta = node.kind;
  if (node.file) meta += ` · ${node.file}${node.lineno ? ":" + node.lineno : ""}`;
  if (node.calls) meta += ` · ${node.calls} call${node.calls === 1 ? "" : "s"}, ${(node.total_time * 1000).toFixed(1)}ms`;

  const editable = canEdit && !!node.file && !!node.lineno && !!node.end_lineno;

  function startEdit() {
    setDraft(node!.full_source);
    setError(null);
    setEditing(true);
  }

  async function save() {
    if (!node || !serveToken || !node.file || !node.lineno || !node.end_lineno) return;
    setSaving(true);
    setError(null);
    try {
      await saveNodeSource(serveToken, {
        file: node.file,
        lineno: node.lineno,
        end_lineno: node.end_lineno,
        source: draft,
      });
      onSaved(node.id, draft);
      setEditing(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <aside id="panel">
      <h2>
        {node.id}
        {edited.has(node.id) && (
          <span className="stale-badge" title="Saved this session — reload to refresh the graph/analysis">
            edited
          </span>
        )}
      </h2>
      <div className="meta">{meta}</div>
      {node.signature && (
        <div className="sig">
          <code>{node.signature}</code>
        </div>
      )}
      {node.type_errors.length > 0 && (
        <>
          <div className="section-title">Type errors ({node.type_errors.length})</div>
          <ul className="diag-list">
            {node.type_errors.map((e, i) => (
              <li key={i} className={`diag-${e.severity}`}>
                line {e.line}: {e.message}
              </li>
            ))}
          </ul>
        </>
      )}
      {node.schema && (
        <>
          <div className="section-title">Fields</div>
          <table className="schema-table">
            <thead>
              <tr>
                <th>name</th>
                <th>type</th>
                <th>default</th>
                <th>req</th>
              </tr>
            </thead>
            <tbody>
              {node.schema.map((f) => (
                <tr key={f.name}>
                  <td>{f.name}</td>
                  <td>{f.type}</td>
                  <td>{f.default !== null ? f.default : "—"}</td>
                  <td>{f.required ? "yes" : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      {node.git && (
        <>
          <div className="section-title">History</div>
          <div className="git-history">
            changed <b>{formatAge(node.git.last_change)}</b> · {node.git.churn} commit
            {node.git.churn === 1 ? "" : "s"} touching this range · <code>{node.git.commit}</code>
          </div>
        </>
      )}
      {node.full_source && (
        <>
          <div className="src-toolbar">
            <span className="section-title">Source</span>
            {editable && !editing && (
              <button className="btn" onClick={startEdit}>
                &#9998; Edit
              </button>
            )}
            {editing && (
              <>
                <button className="btn save" disabled={saving} onClick={save}>
                  {saving ? "Saving..." : "Save"}
                </button>
                <button className="btn cancel" disabled={saving} onClick={() => setEditing(false)}>
                  Cancel
                </button>
              </>
            )}
          </div>
          {error && <div className="diag-error" style={{ marginBottom: 6 }}>{error}</div>}
          {editing ? (
            <div id="monacoHost">
              <Suspense fallback={<pre>Loading editor...</pre>}>
                <MonacoEditor
                  height="320px"
                  language={node.file?.endsWith(".py") ? "python" : "plaintext"}
                  theme={darkMode ? "vs-dark" : "vs"}
                  value={draft}
                  onChange={(v) => setDraft(v ?? "")}
                  options={{ minimap: { enabled: false }, fontSize: 12, scrollBeyondLastLine: false }}
                />
              </Suspense>
            </div>
          ) : (
            <pre id="srcView">{node.full_source}</pre>
          )}
        </>
      )}
      <p className="hint">Click a second node to highlight the call path between them.</p>
    </aside>
  );
}
