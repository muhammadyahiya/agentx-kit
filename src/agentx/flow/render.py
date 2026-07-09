"""Render a :class:`~agentx.flow.model.Flow` as ascii / mermaid / json / dot."""
from __future__ import annotations

from collections import defaultdict

from .model import Flow


def _label(flow: Flow, name: str) -> str:
    node = flow.nodes.get(name)
    if flow.kind != "runtime" or node is None or not node.calls:
        return name
    plural = "" if node.calls == 1 else "s"
    return f"{name}  [{node.calls} call{plural}, {node.total_time * 1000:.1f}ms]"


def _linear_chain(flow: Flow) -> list[str] | None:
    """If the flow (from ``flow.entry``) is a simple path with no branching or
    incoming fan-in along the way, return the ordered node list; else None."""
    if not flow.entry or flow.entry not in flow.nodes:
        return None
    out = defaultdict(list)
    for e in flow.edges:
        out[e.src].append(e.dst)

    order = [flow.entry]
    seen = {flow.entry}
    cur = flow.entry
    while len(out[cur]) == 1:
        nxt = out[cur][0]
        if nxt in seen:
            break   # cycle guard
        order.append(nxt)
        seen.add(nxt)
        cur = nxt
    if len(order) >= 2 and all(len(out[n]) <= 1 for n in order):
        return order
    return None


def _roots(flow: Flow) -> list[str]:
    # Only edges from a *real* node count as "incoming" — the runtime tracer's
    # synthetic "START" pseudo-caller isn't a node, so a top-level traced call
    # must not look like it has an incoming edge.
    has_incoming = {e.dst for e in flow.edges if e.src in flow.nodes}
    roots = [n for n in flow.nodes if n not in has_incoming]
    return roots or (list(flow.nodes)[:1] if flow.nodes else [])


def _walk(name: str, children: dict, flow: Flow, lines: list[str], prefix: str, is_last: bool, visited: frozenset) -> None:
    connector = "└─ " if is_last else "├─ "
    lines.append((prefix + connector + _label(flow, name)) if prefix else _label(flow, name))
    if name in visited:
        return
    visited = visited | {name}
    kids = children.get(name, [])
    new_prefix = prefix + ("   " if is_last else "│  ")
    for i, kid in enumerate(kids):
        _walk(kid, children, flow, lines, new_prefix, i == len(kids) - 1, visited)


def render_ascii(flow: Flow) -> str:
    """A vertical arrow chain for simple linear flows, or an indented tree for
    branching ones (the shape most function-call graphs actually have)."""
    if not flow.nodes:
        return "(no functions found)"

    chain = _linear_chain(flow)
    if chain:
        lines = ["○ Start"]
        for name in chain:
            lines.append(" │")
            lines.append(" ▼")
            lines.append(_label(flow, name))
        return "\n".join(lines)

    children = defaultdict(list)
    for e in flow.edges:
        children[e.src].append(e.dst)
    roots = [flow.entry] if flow.entry else _roots(flow)
    lines: list[str] = []
    for root in roots:
        _walk(root, children, flow, lines, prefix="", is_last=True, visited=frozenset())
    return "\n".join(lines) if lines else "(empty graph)"


def _mm(name: str) -> str:
    safe = name.replace('"', "'")
    return f'{_mm_id(name)}["{safe}"]'


def _mm_id(name: str) -> str:
    return "n_" + "".join(c if c.isalnum() else "_" for c in name)


def render_mermaid(flow: Flow) -> str:
    """Mermaid ``graph TD`` text (paste into a .md file / VS Code / GitHub)."""
    lines = ["graph TD"]
    for e in flow.edges:
        lines.append(f"    {_mm(e.src)} --> {_mm(e.dst)}")
    if not flow.edges:
        for name in flow.nodes:
            lines.append(f"    {_mm(name)}")
    return "\n".join(lines)


def render_json(flow: Flow) -> dict:
    return {
        "kind": flow.kind,
        "entry": flow.entry,
        "nodes": [
            {
                "name": n.name, "file": n.file, "lineno": n.lineno,
                "external": n.external, "calls": n.calls, "total_time": n.total_time,
            }
            for n in flow.nodes.values()
        ],
        "edges": [{"from": e.src, "to": e.dst, "count": e.count} for e in flow.edges],
    }


def render_dot(flow: Flow) -> str:
    """Graphviz DOT text — render with ``dot -Tsvg flow.dot -o flow.svg``."""
    lines = ["digraph G {", "    rankdir=TB;"]
    for name in flow.nodes:
        label = _label(flow, name).replace('"', "'")
        lines.append(f'    "{name}" [label="{label}"];')
    for e in flow.edges:
        lines.append(f'    "{e.src}" -> "{e.dst}";')
    lines.append("}")
    return "\n".join(lines)


__all__ = ["render_ascii", "render_mermaid", "render_json", "render_dot"]
