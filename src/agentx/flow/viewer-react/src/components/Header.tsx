import type { DetailLevel, NodeKind } from "../types";

const LEGEND: { kind: NodeKind; label: string }[] = [
  { kind: "function", label: "function" },
  { kind: "class", label: "class" },
  { kind: "module", label: "module" },
  { kind: "external", label: "external" },
];

interface Props {
  title: string;
  search: string;
  onSearch: (v: string) => void;
  level: DetailLevel;
  onLevel: (l: DetailLevel) => void;
  showLevelToggle: boolean;
  kindFilters: Record<NodeKind, boolean>;
  onToggleKind: (k: NodeKind) => void;
  colors: Record<string, string>;
  darkMode: boolean;
  onToggleTheme: () => void;
  serve: boolean;
  running: boolean;
  onRun: () => void;
  onStop: () => void;
}

export default function Header({
  title,
  search,
  onSearch,
  level,
  onLevel,
  showLevelToggle,
  kindFilters,
  onToggleKind,
  colors,
  darkMode,
  onToggleTheme,
  serve,
  running,
  onRun,
  onStop,
}: Props) {
  return (
    <header>
      <h1>{title}</h1>
      <input
        type="text"
        id="search"
        placeholder="Search nodes..."
        value={search}
        onChange={(e) => onSearch(e.target.value)}
      />
      <div className="legend">
        {LEGEND.map(({ kind, label }) => (
          <span
            key={kind}
            className={`chip${kindFilters[kind] ? "" : " off"}`}
            onClick={() => onToggleKind(kind)}
          >
            <span className="swatch" style={{ background: colors[kind] ?? "#999" }} />
            {label}
          </span>
        ))}
      </div>
      {showLevelToggle && (
        <div className="seg" id="detailSeg">
          {(["modules", "classes", "full"] as DetailLevel[]).map((l) => (
            <button key={l} className={`btn${level === l ? " active" : ""}`} onClick={() => onLevel(l)}>
              {l[0].toUpperCase() + l.slice(1)}
            </button>
          ))}
        </div>
      )}
      <button className="btn" id="themeToggle" onClick={onToggleTheme}>
        {darkMode ? "Light theme" : "Dark theme"}
      </button>
      {serve && !running && (
        <button className="btn run" onClick={onRun} title="Executes this file on your machine">
          &#9654; Run (executes code)
        </button>
      )}
      {serve && running && (
        <button className="btn stop" onClick={onStop}>
          &#9632; Stop
        </button>
      )}
    </header>
  );
}
