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
"""
from .model import Flow, FlowEdge, FlowNode
from .render import render_ascii, render_dot, render_json, render_mermaid
from .static import build_static_flow
from .tracer import get_current_flow, reset_trace, trace

__all__ = [
    "Flow",
    "FlowNode",
    "FlowEdge",
    "build_static_flow",
    "trace",
    "get_current_flow",
    "reset_trace",
    "render_ascii",
    "render_mermaid",
    "render_json",
    "render_dot",
]
