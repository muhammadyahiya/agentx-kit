"""Tests for agentx.flow.typecheck — mypy wrapper + node-diagnostic mapping."""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("mypy")

from agentx.flow import build_static_flow  # noqa: E402
from agentx.flow.typecheck import map_diagnostics_to_nodes, run_mypy  # noqa: E402


def test_run_mypy_reports_type_error(tmp_path: Path) -> None:
    p = tmp_path / "bad.py"
    p.write_text("def add(a: int, b: int) -> int:\n    return a + b\n\nresult: str = add(1, 2)\n", encoding="utf-8")
    diagnostics = run_mypy(p)
    file_key = str(p.resolve())
    assert file_key in diagnostics
    assert diagnostics[file_key][0]["severity"] == "error"
    assert diagnostics[file_key][0]["line"] == 4


def test_run_mypy_clean_file_has_no_diagnostics(tmp_path: Path) -> None:
    p = tmp_path / "good.py"
    p.write_text("def add(a: int, b: int) -> int:\n    return a + b\n", encoding="utf-8")
    diagnostics = run_mypy(p)
    assert diagnostics == {} or str(p.resolve()) not in diagnostics


def test_map_diagnostics_to_nearest_preceding_node(tmp_path: Path) -> None:
    p = tmp_path / "bad.py"
    p.write_text("def add(a: int, b: int) -> int:\n    return a + b\n\nresult: str = add(1, 2)\n", encoding="utf-8")
    flow = build_static_flow(p)
    diagnostics = run_mypy(p)
    mapped = map_diagnostics_to_nodes(flow, diagnostics)
    assert "add" in mapped
    assert mapped["add"][0]["line"] == 4


def test_map_diagnostics_ignores_unrelated_files(tmp_path: Path) -> None:
    p = tmp_path / "good.py"
    p.write_text("def ok():\n    pass\n", encoding="utf-8")
    flow = build_static_flow(p)
    mapped = map_diagnostics_to_nodes(flow, {"/some/other/file.py": [{"line": 1, "severity": "error", "message": "x"}]})
    assert mapped == {}
