"""See your Python code as a DAG — two complementary views.

* **Static** (:func:`build_static_flow`) — parses a file with ``ast`` (nothing
  is imported or executed) and builds a function-call graph. Fast, safe,
  works on any file.
* **Runtime** (:func:`trace` / :func:`get_current_flow`) — decorate functions
  with ``@trace`` and run your code normally; the actual call order, counts,
  and per-call timing are recorded.

Both produce the same :class:`Flow` shape, rendered via ``render_ascii`` /
``render_mermaid`` / ``render_json`` / ``render_dot``::

    from agentx.flow import build_static_flow, render_ascii

    flow = build_static_flow("app.py")
    print(render_ascii(flow))

    from agentx.flow import trace, get_current_flow, render_ascii

    @trace
    def clean(): ...
    @trace
    def train(): ...

    train()
    print(render_ascii(get_current_flow()))

Also available from the CLI: ``agentx flow app.py`` (static) and
``agentx flow app.py --live`` (runs the file, renders the traced graph).

Point it at a directory instead of a file and :func:`build_project_flow`
builds a whole-project graph (packages/modules/classes/functions), which
:func:`render_html` can turn into an interactive 2D/3D DAG viewer —
``agentx flow --ui``.
"""
from .htmlgen import render_html
from .model import Flow, FlowEdge, FlowNode
from .project import build_project_flow
from .render import (
    available_renderers,
    get_renderer,
    register_renderer,
    render_ascii,
    render_dot,
    render_json,
    render_mermaid,
)
from .static import build_static_flow
from .tracer import get_current_flow, reset_trace, trace

__all__ = [
    "Flow",
    "FlowNode",
    "FlowEdge",
    "build_static_flow",
    "build_project_flow",
    "trace",
    "get_current_flow",
    "reset_trace",
    "render_ascii",
    "render_mermaid",
    "render_json",
    "render_dot",
    "render_html",
    "register_renderer",
    "get_renderer",
    "available_renderers",
]
