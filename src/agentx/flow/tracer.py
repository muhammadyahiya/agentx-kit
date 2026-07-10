"""Runtime call tracing — decorate functions with :func:`trace` to record what
*actually* ran: call order, call counts, and per-call wall-clock time.

Complements :func:`agentx.flow.static.build_static_flow`: the static graph
shows every call a function *could* make; the runtime graph shows what it
*did* make, in the order it happened::

    from agentx.flow import trace, get_current_flow, render_ascii

    @trace
    def clean(): ...

    @trace
    def train(): ...

    train()
    print(render_ascii(get_current_flow()))

Works on both sync and async functions. The call stack is stored in a
``contextvars.ContextVar`` so concurrent ``asyncio`` tasks (and threads) each
get their own stack — recursive or concurrent calls don't corrupt each
other's timing.
"""
from __future__ import annotations

import asyncio
import functools
import time
from contextvars import ContextVar
from typing import Any, Callable, TypeVar

from .model import Flow

F = TypeVar("F", bound=Callable[..., Any])

_flow: Flow = Flow(kind="runtime")
_stack: ContextVar[list[str]] = ContextVar("agentx_flow_stack", default=[])
_event_hook: Callable[[dict[str, Any]], None] | None = None


def get_current_flow() -> Flow:
    """Return the process-global runtime :class:`~agentx.flow.model.Flow` recorded so far."""
    return _flow


def reset_trace() -> None:
    """Discard any recorded runtime flow and start fresh."""
    global _flow
    _flow = Flow(kind="runtime")


def set_event_hook(fn: Callable[[dict[str, Any]], None] | None) -> None:
    """Register a callback invoked with a ``{"type": "trace_call"|"trace_return", ...}``
    dict on every traced call/return, in addition to the normal :class:`Flow`
    bookkeeping. Used by ``agentx flow --serve`` to stream execution progress
    to a browser; has no effect on `--live`/library use of `@trace` when unset
    (the default)."""
    global _event_hook
    _event_hook = fn


def _enter(name: str) -> tuple[list[str], float]:
    stack_before = list(_stack.get())
    caller = stack_before[-1] if stack_before else "START"
    _flow.add_node(name)
    _flow.add_edge(caller, name)
    _stack.set([*stack_before, name])
    start = time.perf_counter()
    if _event_hook is not None:
        _event_hook({"type": "trace_call", "node": name, "ts": time.time()})
    return stack_before, start


def _exit(name: str, stack_before: list[str], start: float) -> None:
    elapsed = time.perf_counter() - start
    node = _flow.nodes.get(name)
    if node is not None:
        node.calls += 1
        node.total_time += elapsed
    _stack.set(stack_before)
    if _event_hook is not None:
        _event_hook({"type": "trace_return", "node": name, "elapsed_ms": elapsed * 1000, "ts": time.time()})


def trace(func: F | None = None, *, name: str | None = None) -> F:
    """Decorator: record every call to ``func`` into the current runtime flow.

    Args:
        name: Override the recorded node name (default: ``func.__name__``, so
            e.g. a function nested inside another function is recorded under
            its plain name, not a noisy ``outer.<locals>.inner`` qualname).
            Two differently-scoped functions sharing a name are aggregated
            into one node unless you pass an explicit ``name=`` to tell them
            apart (e.g. ``@trace(name="Pipeline.step")``).
    """

    def _decorate(fn: F) -> F:
        fn_name = name or fn.__name__

        if asyncio.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def _awrapper(*args: Any, **kwargs: Any) -> Any:
                stack_before, start = _enter(fn_name)
                try:
                    return await fn(*args, **kwargs)
                finally:
                    _exit(fn_name, stack_before, start)
            return _awrapper  # type: ignore[return-value]

        @functools.wraps(fn)
        def _wrapper(*args: Any, **kwargs: Any) -> Any:
            stack_before, start = _enter(fn_name)
            try:
                return fn(*args, **kwargs)
            finally:
                _exit(fn_name, stack_before, start)
        return _wrapper  # type: ignore[return-value]

    if func is not None:
        return _decorate(func)
    return _decorate  # type: ignore[return-value]


__all__ = ["trace", "get_current_flow", "reset_trace", "set_event_hook"]
