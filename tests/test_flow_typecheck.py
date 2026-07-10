"""Tests for agentx.flow.typecheck — ruff + ty wrapper + node-diagnostic mapping."""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("ruff")
pytest.importorskip("ty")

from agentx.flow import build_static_flow  # noqa: E402
from agentx.flow.typecheck import map_diagnostics_to_nodes, run_typecheck  # noqa: E402


def test_run_typecheck_reports_type_error(tmp_path: Path) -> None:
    p = tmp_path / "bad.py"
    p.write_text("def add(a: int, b: int) -> int:\n    return a + b\n\nresult: str = add(1, 2)\n", encoding="utf-8")
    diagnostics = run_typecheck(p)
    file_key = str(p.resolve())
    assert file_key in diagnostics
    assert any(d["severity"] == "error" and d["line"] == 4 for d in diagnostics[file_key])


def test_run_typecheck_clean_file_has_no_diagnostics(tmp_path: Path) -> None:
    p = tmp_path / "good.py"
    p.write_text("def add(a: int, b: int) -> int:\n    return a + b\n", encoding="utf-8")
    diagnostics = run_typecheck(p)
    assert diagnostics == {} or str(p.resolve()) not in diagnostics


def test_run_typecheck_reports_ruff_lint_diagnostic(tmp_path: Path) -> None:
    p = tmp_path / "lint.py"
    p.write_text("import os\n\n\ndef ok() -> None:\n    pass\n", encoding="utf-8")
    diagnostics = run_typecheck(p)
    file_key = str(p.resolve())
    assert file_key in diagnostics
    assert any(d["tool"] == "ruff" and d["line"] == 1 for d in diagnostics[file_key])


def test_map_diagnostics_to_nearest_preceding_node(tmp_path: Path) -> None:
    p = tmp_path / "bad.py"
    p.write_text("def add(a: int, b: int) -> int:\n    return a + b\n\nresult: str = add(1, 2)\n", encoding="utf-8")
    flow = build_static_flow(p)
    diagnostics = run_typecheck(p)
    mapped = map_diagnostics_to_nodes(flow, diagnostics)
    assert "add" in mapped
    assert any(d["line"] == 4 for d in mapped["add"])


def test_map_diagnostics_ignores_unrelated_files(tmp_path: Path) -> None:
    p = tmp_path / "good.py"
    p.write_text("def ok():\n    pass\n", encoding="utf-8")
    flow = build_static_flow(p)
    mapped = map_diagnostics_to_nodes(flow, {"/some/other/file.py": [{"line": 1, "severity": "error", "message": "x"}]})
    assert mapped == {}
