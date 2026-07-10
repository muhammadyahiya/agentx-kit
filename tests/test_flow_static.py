"""Tests for agentx.flow.static — AST-based function-call graph builder."""
from __future__ import annotations

from pathlib import Path

import pytest

from agentx.flow import build_static_flow


def _write(tmp_path: Path, source: str) -> Path:
    p = tmp_path / "app.py"
    p.write_text(source, encoding="utf-8")
    return p


def test_linear_chain(tmp_path: Path) -> None:
    p = _write(tmp_path, """
def load_csv():
    pass

def clean_data():
    load_csv()

def validate():
    clean_data()

def preprocess():
    validate()
""")
    flow = build_static_flow(p, entry="preprocess")
    assert set(flow.nodes) == {"preprocess", "validate", "clean_data", "load_csv"}
    assert flow.successors("preprocess") == ["validate"]
    assert flow.successors("validate") == ["clean_data"]
    assert flow.successors("clean_data") == ["load_csv"]


def test_branching_calls(tmp_path: Path) -> None:
    p = _write(tmp_path, """
def load_csv():
    pass

def clean_data():
    pass

def validate():
    pass

def preprocess():
    load_csv()
    clean_data()
    validate()
""")
    flow = build_static_flow(p, entry="preprocess")
    assert set(flow.successors("preprocess")) == {"load_csv", "clean_data", "validate"}


def test_module_level_entry_inferred(tmp_path: Path) -> None:
    p = _write(tmp_path, """
def preprocess():
    pass

def train():
    preprocess()

if __name__ == "__main__":
    train()
""")
    flow = build_static_flow(p)
    assert flow.entry == "__main__"
    assert "train" in flow.successors("__main__")


def test_no_entry_returns_whole_file_graph(tmp_path: Path) -> None:
    p = _write(tmp_path, """
def a():
    b()

def b():
    pass

def unrelated():
    pass
""")
    flow = build_static_flow(p)
    assert set(flow.nodes) == {"a", "b", "unrelated"}
    assert flow.successors("a") == ["b"]


def test_unknown_entry_raises(tmp_path: Path) -> None:
    p = _write(tmp_path, "def a():\n    pass\n")
    with pytest.raises(ValueError, match="not found"):
        build_static_flow(p, entry="does_not_exist")


def test_external_calls_included_by_default(tmp_path: Path) -> None:
    p = _write(tmp_path, """
import xgboost

def train():
    xgboost.fit()
""")
    flow = build_static_flow(p, entry="train")
    assert "xgboost.fit" in flow.nodes
    assert flow.nodes["xgboost.fit"].external is True
    assert flow.successors("train") == ["xgboost.fit"]


def test_external_calls_excluded_when_disabled(tmp_path: Path) -> None:
    p = _write(tmp_path, """
import xgboost

def train():
    xgboost.fit()
""")
    flow = build_static_flow(p, entry="train", include_external=False)
    assert "xgboost.fit" not in flow.nodes
    assert flow.successors("train") == []


def test_class_methods_get_qualified_names(tmp_path: Path) -> None:
    p = _write(tmp_path, """
class Pipeline:
    def run(self):
        self.step()

    def step(self):
        pass
""")
    flow = build_static_flow(p)
    assert "Pipeline.run" in flow.nodes
    assert "Pipeline.step" in flow.nodes
    # bare-name resolution: self.step() -> "step" resolves to "Pipeline.step"
    assert flow.successors("Pipeline.run") == ["Pipeline.step"]


def test_async_functions_are_collected(tmp_path: Path) -> None:
    p = _write(tmp_path, """
async def fetch():
    pass

async def main():
    await fetch()
""")
    flow = build_static_flow(p, entry="main")
    assert flow.successors("main") == ["fetch"]


def test_recursive_function_self_edge(tmp_path: Path) -> None:
    p = _write(tmp_path, """
def factorial(n):
    if n <= 1:
        return 1
    return n * factorial(n - 1)
""")
    flow = build_static_flow(p, entry="factorial")
    assert flow.successors("factorial") == ["factorial"]


def test_nested_function_calls_are_not_attributed_to_outer_function(tmp_path: Path) -> None:
    # Regression test: a call made only inside a nested `def inner(): ...`
    # must not also show up as a call made by the enclosing function — the
    # inner def is its own node with its own call graph.
    p = _write(tmp_path, """
def only_in_inner():
    pass

def outer():
    def inner():
        only_in_inner()
    return inner
""")
    flow = build_static_flow(p)
    assert flow.successors("outer") == []
    assert flow.successors("outer.inner") == ["only_in_inner"]


def test_syntax_error_raises_clean_value_error(tmp_path: Path) -> None:
    p = _write(tmp_path, "def broken(: pass\n")
    with pytest.raises(ValueError, match="Syntax error"):
        build_static_flow(p)
