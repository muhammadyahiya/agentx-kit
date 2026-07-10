"""Tests for agentx.flow.project — whole-project, multi-file call-graph builder."""
from __future__ import annotations

from pathlib import Path

import pytest

from agentx.flow import build_project_flow


def _write(root: Path, rel: str, source: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(source, encoding="utf-8")
    return p


def _make_pkg(root: Path) -> Path:
    """Populate ``root`` with a ``pkg`` package and return ``root`` itself —
    ``build_project_flow``'s ``root`` argument IS the top-level namespace, so
    passing ``root`` (not ``root / "pkg"``) keeps the ``pkg.`` prefix on names."""
    _write(root, "pkg/__init__.py", "")
    _write(root, "pkg/a.py", """
def foo():
    pass
""")
    _write(root, "pkg/b.py", """
from .a import foo

def bar():
    foo()
""")
    _write(root, "pkg/sub/__init__.py", "")
    _write(root, "pkg/sub/c.py", """
from ..a import foo

class Worker:
    def run(self):
        self.step()
        foo()

    def step(self):
        pass
""")
    return root


def test_module_class_function_kinds_and_parents(tmp_path: Path) -> None:
    pkg = _make_pkg(tmp_path)
    flow = build_project_flow(pkg)

    assert flow.scope == "project"
    assert flow.nodes["pkg"].kind == "package"
    assert flow.nodes["pkg"].parent is None
    assert flow.nodes["pkg.a"].kind == "module"
    assert flow.nodes["pkg.a"].parent == "pkg"
    assert flow.nodes["pkg.a.foo"].kind == "function"
    assert flow.nodes["pkg.a.foo"].parent == "pkg.a"
    assert flow.nodes["pkg.sub"].kind == "package"
    assert flow.nodes["pkg.sub"].parent == "pkg"
    assert flow.nodes["pkg.sub.c.Worker"].kind == "class"
    assert flow.nodes["pkg.sub.c.Worker"].parent == "pkg.sub.c"
    assert flow.nodes["pkg.sub.c.Worker.run"].kind == "function"
    assert flow.nodes["pkg.sub.c.Worker.run"].parent == "pkg.sub.c.Worker"


def test_every_parent_reference_points_to_a_real_node(tmp_path: Path) -> None:
    # Invariant the HTML viewer depends on: a compound-node `parent` must
    # always resolve to another node actually present in the graph.
    pkg = _make_pkg(tmp_path)
    flow = build_project_flow(pkg)
    for node in flow.nodes.values():
        if node.parent is not None:
            assert node.parent in flow.nodes


def test_cross_file_import_resolves_to_real_node(tmp_path: Path) -> None:
    pkg = _make_pkg(tmp_path)
    flow = build_project_flow(pkg)
    assert "pkg.a.foo" in flow.successors("pkg.b.bar")


def test_relative_import_two_levels_up_resolves(tmp_path: Path) -> None:
    pkg = _make_pkg(tmp_path)
    flow = build_project_flow(pkg)
    assert "pkg.a.foo" in flow.successors("pkg.sub.c.Worker.run")


def test_self_method_call_still_resolves_within_project_scope(tmp_path: Path) -> None:
    pkg = _make_pkg(tmp_path)
    flow = build_project_flow(pkg)
    assert "pkg.sub.c.Worker.step" in flow.successors("pkg.sub.c.Worker.run")


def test_excludes_venv_and_pycache_dirs(tmp_path: Path) -> None:
    pkg = _make_pkg(tmp_path)
    _write(tmp_path, "pkg/.venv/site-packages/injected.py", "def should_not_appear():\n    pass\n")
    _write(tmp_path, "pkg/__pycache__/stale.py", "def also_should_not_appear():\n    pass\n")
    flow = build_project_flow(pkg)
    assert not any("should_not_appear" in name for name in flow.nodes)


def test_binary_file_with_py_extension_is_skipped_not_fatal(tmp_path: Path) -> None:
    pkg = _make_pkg(tmp_path)
    binary_path = tmp_path / "pkg" / "not_really_python.py"
    binary_path.write_bytes(b"\xff\xfe\x00\x01binary garbage, not utf-8 \x80\x81")
    # Must not raise UnicodeDecodeError — the rest of the project still builds.
    flow = build_project_flow(pkg)
    assert "pkg.a.foo" in flow.nodes


def test_unreadable_file_is_skipped_not_fatal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # chmod-based "unreadable file" tests are unreliable across platforms
    # (root ignores permission bits; Windows chmod semantics differ), so
    # simulate the OSError directly instead.
    pkg = _make_pkg(tmp_path)
    locked = tmp_path / "pkg" / "locked.py"
    locked.write_text("def locked_fn():\n    pass\n", encoding="utf-8")

    real_read_text = Path.read_text

    def fake_read_text(self, *args, **kwargs):
        if self == locked:
            raise PermissionError(f"simulated: permission denied for {self}")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fake_read_text)
    flow = build_project_flow(pkg)
    assert "pkg.a.foo" in flow.nodes
    assert not any("locked_fn" in name for name in flow.nodes)


def test_include_tests_flag(tmp_path: Path) -> None:
    pkg = _make_pkg(tmp_path)
    _write(tmp_path, "pkg/tests/test_a.py", """
def test_something():
    pass
""")
    with_tests = build_project_flow(pkg, include_tests=True)
    without_tests = build_project_flow(pkg, include_tests=False)
    assert any(name.endswith("test_a.test_something") for name in with_tests.nodes)
    assert not any(name.endswith("test_a.test_something") for name in without_tests.nodes)


def test_external_calls_included_by_default(tmp_path: Path) -> None:
    pkg = _make_pkg(tmp_path)
    _write(tmp_path, "pkg/c.py", """
import xgboost

def train():
    xgboost.fit()
""")
    flow = build_project_flow(pkg)
    assert any(n.external and n.kind == "external" for n in flow.nodes.values() if "xgboost" in n.name)


def test_external_calls_excluded_when_disabled(tmp_path: Path) -> None:
    pkg = _make_pkg(tmp_path)
    _write(tmp_path, "pkg/c.py", """
import xgboost

def train():
    xgboost.fit()
""")
    flow = build_project_flow(pkg, include_external=False)
    assert not any("xgboost" in name for name in flow.nodes)


def test_entry_scopes_to_reachable_subgraph(tmp_path: Path) -> None:
    pkg = _make_pkg(tmp_path)
    flow = build_project_flow(pkg, entry="bar")
    assert flow.scope == "project"
    assert "pkg.b.bar" in flow.nodes
    assert "pkg.a.foo" in flow.nodes
    assert "pkg.sub.c.Worker.run" not in flow.nodes


def test_unknown_entry_raises(tmp_path: Path) -> None:
    pkg = _make_pkg(tmp_path)
    with pytest.raises(ValueError, match="not found"):
        build_project_flow(pkg, entry="does_not_exist")


def test_max_files_guard_raises_before_scanning(tmp_path: Path) -> None:
    pkg = _make_pkg(tmp_path)
    with pytest.raises(ValueError, match="max_files"):
        build_project_flow(pkg, max_files=1)


def test_star_import_warns_but_does_not_crash(tmp_path: Path) -> None:
    _write(tmp_path, "pkg_star/__init__.py", "")
    _write(tmp_path, "pkg_star/helpers.py", "def helper():\n    pass\n")
    _write(tmp_path, "pkg_star/main.py", """
from .helpers import *

def use():
    helper()
""")
    with pytest.warns(UserWarning, match="import \\*"):
        flow = build_project_flow(tmp_path)
    assert "pkg_star.main.use" in flow.nodes


def test_circular_import_between_two_modules_warns(tmp_path: Path) -> None:
    _write(tmp_path, "pkg_cycle/__init__.py", "")
    _write(tmp_path, "pkg_cycle/a.py", """
from .b import bar

def foo():
    bar()
""")
    _write(tmp_path, "pkg_cycle/b.py", """
from .a import foo

def bar():
    pass
""")
    with pytest.warns(UserWarning, match="Circular import"):
        build_project_flow(tmp_path)
