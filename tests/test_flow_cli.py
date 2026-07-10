"""Tests for the `agentx flow` CLI command (static + --live modes)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from agentx.cli import app

runner = CliRunner()


def _write(tmp_path: Path, name: str, source: str) -> Path:
    p = tmp_path / name
    p.write_text(source, encoding="utf-8")
    return p


def test_static_ascii_default(tmp_path: Path) -> None:
    p = _write(tmp_path, "app.py", """
def load_csv():
    pass

def clean_data():
    load_csv()

def train():
    clean_data()

if __name__ == "__main__":
    train()
""")
    result = runner.invoke(app, ["flow", str(p)])
    assert result.exit_code == 0
    assert "train" in result.output
    assert "clean_data" in result.output
    assert "load_csv" in result.output


def test_static_entry_scopes_subgraph(tmp_path: Path) -> None:
    p = _write(tmp_path, "app.py", """
def helper():
    pass

def main_flow():
    helper()

def unrelated():
    pass
""")
    result = runner.invoke(app, ["flow", str(p), "--entry", "main_flow"])
    assert result.exit_code == 0
    assert "helper" in result.output
    assert "unrelated" not in result.output


def test_static_json_format(tmp_path: Path) -> None:
    p = _write(tmp_path, "app.py", "def a():\n    pass\n")
    result = runner.invoke(app, ["flow", str(p), "-f", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["kind"] == "static"
    assert any(n["name"] == "a" for n in data["nodes"])


def test_static_mermaid_format_not_corrupted(tmp_path: Path) -> None:
    p = _write(tmp_path, "app.py", "def a():\n    b()\n\ndef b():\n    pass\n")
    result = runner.invoke(app, ["flow", str(p), "--entry", "a", "-f", "mermaid"])
    assert result.exit_code == 0
    assert result.output.startswith("graph TD")
    assert 'n_a["a"] --> n_b["b"]' in result.output


def test_static_dot_format_not_corrupted_by_rich_markup(tmp_path: Path) -> None:
    p = _write(tmp_path, "app.py", "def a():\n    pass\n")
    result = runner.invoke(app, ["flow", str(p), "-f", "dot"])
    assert result.exit_code == 0
    # Regression: Rich console markup parsing must not eat the [label=...] part.
    assert '[label="a"]' in result.output


def test_unknown_format_errors_with_available_list(tmp_path: Path) -> None:
    p = _write(tmp_path, "app.py", "def a():\n    pass\n")
    result = runner.invoke(app, ["flow", str(p), "-f", "yaml"])
    assert result.exit_code == 1
    assert "Unknown format" in result.output
    assert "ascii" in result.output and "mermaid" in result.output


def test_static_unknown_entry_errors(tmp_path: Path) -> None:
    p = _write(tmp_path, "app.py", "def a():\n    pass\n")
    result = runner.invoke(app, ["flow", str(p), "--entry", "nope"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_missing_file_errors(tmp_path: Path) -> None:
    result = runner.invoke(app, ["flow", str(tmp_path / "nope.py")])
    assert result.exit_code == 1
    assert "Path not found" in result.output


def test_live_mode_runs_file_and_shows_traced_calls(tmp_path: Path) -> None:
    p = _write(tmp_path, "live_app.py", """
from agentx.flow import trace

@trace
def clean():
    pass

@trace
def train():
    clean()
    clean()

if __name__ == "__main__":
    train()
""")
    result = runner.invoke(app, ["flow", str(p), "--live"])
    assert result.exit_code == 0
    assert "train" in result.output
    assert "2 calls" in result.output  # clean() called twice


def test_live_mode_no_trace_decorators_warns_and_exits_nonzero(tmp_path: Path) -> None:
    # A misconfigured --live run (no @trace decorators anywhere in the target)
    # must exit nonzero, not 0 — otherwise CI/scripts can't tell it apart from
    # a successful run that happened to trace nothing.
    p = _write(tmp_path, "plain.py", """
def hello():
    pass

if __name__ == "__main__":
    hello()
""")
    result = runner.invoke(app, ["flow", str(p), "--live"])
    assert result.exit_code == 1
    assert "No traced calls recorded" in result.output


def test_directory_path_builds_project_graph(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/a.py", "def foo():\n    pass\n")
    result = runner.invoke(app, ["flow", str(tmp_path), "-f", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["kind"] == "static"
    assert any(n["name"] == "pkg.a.foo" for n in data["nodes"])


def test_default_path_is_current_directory(tmp_path: Path, monkeypatch) -> None:
    _write(tmp_path, "solo.py", "def only():\n    pass\n")
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["flow", "-f", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert any(n["name"] == "solo.only" for n in data["nodes"])


def test_live_mode_rejects_directory(tmp_path: Path) -> None:
    result = runner.invoke(app, ["flow", str(tmp_path), "--live"])
    assert result.exit_code == 1
    assert "single file" in result.output.lower()


def test_ui_flag_writes_html_and_skips_browser(tmp_path: Path) -> None:
    p = _write(tmp_path, "app.py", "def a():\n    pass\n")
    out = tmp_path / "viewer.html"
    result = runner.invoke(app, ["flow", str(p), "--ui", "--no-open", "--out", str(out)])
    assert result.exit_code == 0
    assert out.exists()
    html = out.read_text(encoding="utf-8")
    assert "cytoscape" in html
    assert '"a"' in html


def test_ui_flag_without_out_writes_temp_file(tmp_path: Path) -> None:
    p = _write(tmp_path, "app.py", "def a():\n    pass\n")
    result = runner.invoke(app, ["flow", str(p), "--ui", "--no-open"])
    assert result.exit_code == 0
    assert "Wrote" in result.output
    # Rich may hard-wrap a long path across lines; rejoin before parsing it out.
    flat = result.output.replace("\n", "")
    written = Path(flat.split("Wrote")[1].strip())
    assert written.exists()
    written.unlink()


def test_ui_cdn_flag_references_cdn_instead_of_inlining(tmp_path: Path) -> None:
    p = _write(tmp_path, "app.py", "def a():\n    pass\n")
    out = tmp_path / "viewer.html"
    result = runner.invoke(app, ["flow", str(p), "--ui", "--cdn", "--no-open", "--out", str(out)])
    assert result.exit_code == 0
    html = out.read_text(encoding="utf-8")
    assert "cdn.jsdelivr.net" in html


def test_no_external_flag_excludes_stdlib_calls(tmp_path: Path) -> None:
    p = _write(tmp_path, "app.py", """
import json

def dump():
    json.dumps({})
""")
    with_ext = runner.invoke(app, ["flow", str(p), "--entry", "dump", "-f", "json"])
    without_ext = runner.invoke(app, ["flow", str(p), "--entry", "dump", "--no-external", "-f", "json"])
    assert any(n["name"] == "json.dumps" for n in json.loads(with_ext.output)["nodes"])
    assert not any(n["name"] == "json.dumps" for n in json.loads(without_ext.output)["nodes"])


def test_max_files_guard_rejects_oversized_project(tmp_path: Path) -> None:
    _write(tmp_path, "a.py", "def a():\n    pass\n")
    _write(tmp_path, "b.py", "def b():\n    pass\n")
    result = runner.invoke(app, ["flow", str(tmp_path), "--max-files", "1"])
    assert result.exit_code == 1
    assert "max_files" in result.output or "--max-files" in result.output


def test_live_and_serve_together_rejected(tmp_path: Path) -> None:
    p = _write(tmp_path, "app.py", "def a():\n    pass\n")
    result = runner.invoke(app, ["flow", str(p), "--live", "--serve"])
    assert result.exit_code == 1
    assert "two different execution modes" in result.output


def test_serve_on_directory_rejected(tmp_path: Path) -> None:
    _write(tmp_path, "a.py", "def a():\n    pass\n")
    result = runner.invoke(app, ["flow", str(tmp_path), "--serve"])
    assert result.exit_code == 1
    assert "single file" in result.output


def test_serve_with_out_rejected(tmp_path: Path) -> None:
    p = _write(tmp_path, "app.py", "def a():\n    pass\n")
    result = runner.invoke(app, ["flow", str(p), "--serve", "--out", str(tmp_path / "x.html")])
    assert result.exit_code == 1
    assert "--out" in result.output


def test_typecheck_missing_deps_prints_install_hint(tmp_path: Path, monkeypatch) -> None:
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "ruff":
            raise ImportError("simulated: ruff not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    p = _write(tmp_path, "app.py", "def a():\n    pass\n")
    result = runner.invoke(app, ["flow", str(p), "--typecheck"])
    assert result.exit_code == 1
    assert "agentx-kit[typecheck]" in result.output


def test_typecheck_reports_error_count(tmp_path: Path) -> None:
    pytest.importorskip("ruff")
    pytest.importorskip("ty")
    p = _write(tmp_path, "bad.py", "def add(a: int, b: int) -> int:\n    return a + b\n\nresult: str = add(1, 2)\n")
    result = runner.invoke(app, ["flow", str(p), "--typecheck", "-f", "json"])
    assert result.exit_code == 0
    assert "ruff + ty:" in result.output
    assert "error" in result.output
