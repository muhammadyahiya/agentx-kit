import { useCallback, useRef, useState } from "react";
import { startRun, stopRun, streamUrl } from "../api";
import type { RunEvent } from "../types";

export interface LogEntry {
  cls: "log-stdout" | "log-stderr" | "log-trace" | "log-info";
  text: string;
}

/** Mirrors the `--serve` branch at the bottom of ../../viewer/app.js: POST
 * /api/run, subscribe to /api/stream/<run_id> over SSE, POST /api/stop. Node
 * running/done pulses are surfaced via `nodeStatus` for the canvas to apply
 * as a class/style on the matching React Flow node. */
export function useLiveExec(token: string | null) {
  const [running, setRunning] = useState(false);
  const [log, setLog] = useState<LogEntry[]>([]);
  const [nodeStatus, setNodeStatus] = useState<Record<string, "running" | "done">>({});
  const currentRunId = useRef<string | null>(null);
  const evtSourceRef = useRef<EventSource | null>(null);

  const appendLog = useCallback((entry: LogEntry) => {
    setLog((prev) => [...prev, entry]);
  }, []);

  const run = useCallback(
    async (command: string | null) => {
      if (!token || running) return;
      setLog([]);
      setNodeStatus({});
      setRunning(true);
      appendLog({ cls: "log-info", text: command ? `$ ${command}` : "Starting run..." });
      try {
        const { run_id } = await startRun(token, command);
        currentRunId.current = run_id;
        const es = new EventSource(streamUrl(token, run_id));
        evtSourceRef.current = es;
        es.onmessage = (e) => {
          const ev = JSON.parse(e.data) as RunEvent;
          if (ev.type === "stdout") appendLog({ cls: "log-stdout", text: ev.text });
          else if (ev.type === "stderr") appendLog({ cls: "log-stderr", text: ev.text });
          else if (ev.type === "trace_call") {
            appendLog({ cls: "log-trace", text: `→ ${ev.node}` });
            setNodeStatus((prev) => ({ ...prev, [ev.node]: "running" }));
          } else if (ev.type === "trace_return") {
            appendLog({ cls: "log-trace", text: `← ${ev.node} (${ev.elapsed_ms.toFixed(1)}ms)` });
            setNodeStatus((prev) => ({ ...prev, [ev.node]: "done" }));
          } else if (ev.type === "error") {
            appendLog({ cls: "log-stderr", text: `ERROR: ${ev.message}` });
          } else if (ev.type === "done") {
            appendLog({ cls: "log-info", text: `Process exited (code ${ev.exit_code}).` });
            setRunning(false);
            es.close();
          }
        };
        es.onerror = () => {
          // Let the "done" event (or its absence) be the source of truth; a
          // transient onerror shouldn't itself flip `running` off mid-stream.
        };
      } catch (err) {
        appendLog({ cls: "log-stderr", text: `Failed to start: ${(err as Error).message}` });
        setRunning(false);
      }
    },
    [token, running, appendLog],
  );

  const stop = useCallback(async () => {
    if (token && currentRunId.current) await stopRun(token, currentRunId.current);
  }, [token]);

  return { running, log, nodeStatus, run, stop };
}
