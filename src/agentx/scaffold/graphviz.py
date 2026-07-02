"""Render a generated project's structure and agent flow from its manifest.

Powers ``agentx graph``. Pure/testable: everything is derived from ``agentx.json``
(plus ``prompts.json`` for per-agent detail) so it works with zero project
dependencies installed. ``introspect_mermaid`` optionally imports the compiled
LangGraph for a ground-truth diagram.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Flow:
    """A minimal node/edge graph derived from the manifest."""

    nodes: list[str] = field(default_factory=list)
    edges: list[tuple[str, str]] = field(default_factory=list)  # (src, dst)


def load_manifest(project: Path | None) -> tuple[Path, dict]:
    """Walk up from ``project``/cwd to find ``agentx.json``; return (root, parsed).

    Raises FileNotFoundError if no manifest is found.
    """
    base = (project or Path.cwd()).expanduser().resolve()
    for parent in [base, *base.parents]:
        mf = parent / "agentx.json"
        if mf.exists():
            return parent, json.loads(mf.read_text(encoding="utf-8"))
    raise FileNotFoundError(
        f"No agentx.json found from {base}. Run inside a generated AgentX project "
        "or pass --project."
    )


def _load_prompts(root: Path) -> dict:
    for candidate in (root / "prompts.json", *root.glob("src/*/prompts.json")):
        if candidate.exists():
            try:
                return json.loads(candidate.read_text(encoding="utf-8")).get("agents", {})
            except Exception:  # noqa: BLE001
                return {}
    return {}


def build_flow(manifest: dict) -> Flow:
    """Derive the node/edge flow, mirroring the generated graph.py wiring."""
    agents = manifest.get("agents", []) or ["assistant"]
    orchestration = manifest.get("orchestration", "supervisor")
    framework = manifest.get("framework", "langgraph")

    flow = Flow()

    if framework == "crewai":
        # CrewAI runs a sequential crew.
        flow.nodes = ["START", *agents, "END"]
        chain = ["START", *agents, "END"]
        flow.edges = [(chain[i], chain[i + 1]) for i in range(len(chain) - 1)]
        return flow

    if len(agents) <= 1:
        name = agents[0] if agents else "agent"
        flow.nodes = ["START", name, "tools", "END"]
        flow.edges = [("START", name), (name, "tools"), ("tools", name), (name, "END")]
        return flow

    if orchestration == "sequential":
        chain = ["START", *agents, "END"]
        flow.nodes = chain
        flow.edges = [(chain[i], chain[i + 1]) for i in range(len(chain) - 1)]
    elif orchestration == "parallel":
        flow.nodes = ["START", *agents, "merge", "END"]
        flow.edges = [("START", a) for a in agents]
        flow.edges += [(a, "merge") for a in agents]
        flow.edges.append(("merge", "END"))
    else:  # supervisor
        flow.nodes = ["START", "supervisor", *agents, "END"]
        flow.edges = [("START", "supervisor")]
        flow.edges += [("supervisor", a) for a in agents]
        flow.edges += [(a, "supervisor") for a in agents]
        flow.edges.append(("supervisor", "END"))
    return flow


def _feature_summary(manifest: dict) -> list[str]:
    f = manifest.get("features", {})
    bits: list[str] = []
    if f.get("rag"):
        vs = f.get("vector_store") or "chroma"
        emb = f.get("embedding_provider") or "auto"
        bits.append(f"RAG ({vs}/{emb})")
    if f.get("memory") and f.get("memory") != "none":
        bits.append(f"memory={f['memory']}")
    if f.get("mcp"):
        bits.append("MCP")
    if f.get("skills"):
        bits.append("skills")
    if f.get("observability"):
        bits.append("observability")
    if f.get("guardrails"):
        bits.append("guardrails")
    if f.get("serve"):
        bits.append("FastAPI")
    if f.get("cache"):
        bits.append("cache")
    return bits


def render_ascii(manifest: dict, flow: Flow) -> str:
    """Human-readable tree + flow summary."""
    name = manifest.get("name", "project")
    framework = manifest.get("framework", "langgraph")
    orchestration = manifest.get("orchestration", "")
    provider = manifest.get("provider", "")
    model = manifest.get("model", "")
    prompts = _load_prompts(Path.cwd()) if False else {}

    lines = [f"{name}  ({framework}"
             + (f" · {orchestration}" if len(manifest.get('agents', [])) > 1 else "")
             + f" · {provider}/{model})"]
    lines.append("├─ Agents")
    agents = manifest.get("agents", [])
    agent_meta = manifest.get("agents_meta", {})  # optional richer detail
    for i, a in enumerate(agents):
        branch = "│  └─" if i == len(agents) - 1 else "│  ├─"
        meta = agent_meta.get(a, {}) if isinstance(agent_meta, dict) else {}
        extra = ""
        if meta.get("tools"):
            extra += f"   tools: {', '.join(meta['tools'])}"
        if meta.get("skills"):
            extra += f"   skills: {', '.join(meta['skills'])}"
        lines.append(f"{branch} {a}{extra}")
    feats = _feature_summary(manifest)
    lines.append(f"├─ Features: {' · '.join(feats) if feats else '(none)'}")
    lines.append("└─ Flow")
    lines.append("   " + _flow_oneline(flow, manifest))
    return "\n".join(lines)


def _flow_oneline(flow: Flow, manifest: dict) -> str:
    orchestration = manifest.get("orchestration", "")
    agents = manifest.get("agents", [])
    if manifest.get("framework") == "crewai" or orchestration == "sequential":
        return " → ".join(flow.nodes)
    if orchestration == "parallel":
        return f"START → {{{', '.join(agents)}}} → merge → END"
    if len(agents) > 1:  # supervisor
        return f"START → supervisor ⇄ {{{', '.join(agents)}}} → END"
    name = agents[0] if agents else "agent"
    return f"START → {name} ⇄ tools → END"


def render_mermaid(manifest: dict, flow: Flow) -> str:
    """Mermaid ``graph TD`` text (renderable in the VS Code webview / GitHub)."""
    lines = ["graph TD"]
    seen = set()
    for src, dst in flow.edges:
        lines.append(f"    {_mm(src)} --> {_mm(dst)}")
        seen.update((src, dst))
    return "\n".join(lines)


def _mm(node: str) -> str:
    if node in ("START", "END"):
        return f"{node}([{node}])"
    return f"{node}[{node}]"


def render_json(manifest: dict, flow: Flow) -> dict:
    return {
        "name": manifest.get("name"),
        "framework": manifest.get("framework"),
        "orchestration": manifest.get("orchestration"),
        "provider": manifest.get("provider"),
        "model": manifest.get("model"),
        "agents": manifest.get("agents", []),
        "features": manifest.get("features", {}),
        "nodes": flow.nodes,
        "edges": [{"from": s, "to": d} for s, d in flow.edges],
    }


def introspect_mermaid(root: Path, manifest: dict) -> str | None:
    """Import the compiled LangGraph and return its real draw_mermaid(), or None.

    Best-effort — returns None on any import/attribute failure so the caller can
    fall back to the manifest-derived mermaid.
    """
    if manifest.get("framework") != "langgraph":
        return None
    import importlib
    import sys

    pkg = manifest.get("name", "").replace("-", "_")
    src = root / "src"
    added = False
    try:
        if src.exists() and str(src) not in sys.path:
            sys.path.insert(0, str(src))
            added = True
        mod = importlib.import_module(f"{pkg}.graph")
        graph = getattr(mod, "graph", None)
        if graph is None:
            return None
        return graph.get_graph().draw_mermaid()
    except Exception:  # noqa: BLE001
        return None
    finally:
        if added:
            try:
                sys.path.remove(str(src))
            except ValueError:
                pass
