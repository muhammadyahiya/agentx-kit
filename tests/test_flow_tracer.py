"""Tests for agentx.flow.tracer — the @trace runtime call recorder."""
from __future__ import annotations

import asyncio

from agentx.flow import get_current_flow, reset_trace, trace


def setup_function() -> None:
    reset_trace()


def test_simple_call_recorded() -> None:
    @trace
    def hello():
        return "hi"

    assert hello() == "hi"
    flow = get_current_flow()
    assert flow.kind == "runtime"
    assert "hello" in flow.nodes
    assert flow.nodes["hello"].calls == 1
    assert ("START", "hello") in [(e.src, e.dst) for e in flow.edges]


def test_nested_calls_build_edge() -> None:
    @trace
    def inner():
        pass

    @trace
    def outer():
        inner()

    outer()
    flow = get_current_flow()
    assert flow.successors("outer") == ["inner"]
    assert flow.nodes["outer"].calls == 1
    assert flow.nodes["inner"].calls == 1


def test_repeated_calls_aggregate_count_and_time() -> None:
    @trace
    def work():
        pass

    for _ in range(5):
        work()
    flow = get_current_flow()
    assert flow.nodes["work"].calls == 5
    edge = next(e for e in flow.edges if e.src == "START" and e.dst == "work")
    assert edge.count == 5


def test_timing_is_positive() -> None:
    import time

    @trace
    def slow():
        time.sleep(0.01)

    slow()
    flow = get_current_flow()
    assert flow.nodes["slow"].total_time >= 0.01


def test_recursive_function_self_edge() -> None:
    @trace
    def fact(n):
        if n <= 1:
            return 1
        return n * fact(n - 1)

    fact(4)
    flow = get_current_flow()
    assert flow.nodes["fact"].calls == 4
    self_edge = next((e for e in flow.edges if e.src == "fact" and e.dst == "fact"), None)
    assert self_edge is not None
    assert self_edge.count == 3   # fact->fact called 3 times (4->3->2->1)


def test_async_function_traced() -> None:
    @trace
    async def fetch():
        await asyncio.sleep(0.001)
        return 42

    result = asyncio.run(fetch())
    assert result == 42
    flow = get_current_flow()
    assert flow.nodes["fetch"].calls == 1
    assert flow.nodes["fetch"].total_time >= 0.001


def test_async_nested_calls() -> None:
    @trace
    async def load():
        await asyncio.sleep(0.001)

    @trace
    async def clean():
        await load()

    asyncio.run(clean())
    flow = get_current_flow()
    assert flow.successors("clean") == ["load"]


def test_concurrent_asyncio_tasks_do_not_corrupt_stack() -> None:
    @trace
    async def work(n: int) -> int:
        await asyncio.sleep(0.001 * n)
        return n

    @trace
    async def orchestrate():
        return await asyncio.gather(work(1), work(2), work(3))

    asyncio.run(orchestrate())
    flow = get_current_flow()
    assert flow.nodes["work"].calls == 3
    edge = next(e for e in flow.edges if e.src == "orchestrate" and e.dst == "work")
    assert edge.count == 3


def test_reset_trace_clears_state() -> None:
    @trace
    def a():
        pass

    a()
    assert get_current_flow().nodes
    reset_trace()
    assert get_current_flow().nodes == {}


def test_custom_name_override() -> None:
    @trace(name="renamed")
    def original():
        pass

    original()
    flow = get_current_flow()
    assert "renamed" in flow.nodes
    assert "original" not in flow.nodes
