import { useEffect, useRef, useState } from "react";
import type { LogEntry } from "../hooks/useLiveExec";

interface Props {
  visible: boolean;
  log: LogEntry[];
  running: boolean;
  onClose: () => void;
  onRunCommand: (command: string) => void;
}

export default function LogPane({ visible, log, running, onClose, onRunCommand }: Props) {
  const bodyRef = useRef<HTMLDivElement>(null);
  const [cmd, setCmd] = useState("");

  useEffect(() => {
    if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
  }, [log]);

  if (!visible) return null;

  return (
    <div id="logPane" style={{ display: "flex" }}>
      <div className="log-header">
        <span>Execution log</span>
        <button className="btn-mini" onClick={onClose}>
          &times;
        </button>
      </div>
      <div id="logBody" ref={bodyRef}>
        {log.map((entry, i) => (
          <div key={i} className={`log-line ${entry.cls}`}>
            {entry.text}
          </div>
        ))}
      </div>
      <div className="term-bar">
        <span className="term-prompt">$</span>
        <input
          id="termInput"
          placeholder="Run a command, e.g. python main.py (executes on your machine)"
          disabled={running}
          value={cmd}
          onChange={(e) => setCmd(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && cmd.trim()) {
              onRunCommand(cmd.trim());
              setCmd("");
            }
          }}
        />
      </div>
    </div>
  );
}
