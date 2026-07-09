"""Tests for the `agentx flow` CLI command (static + --live modes)."""
from __future__ import annotations

import json
from pathlib import Path

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


def test_static_unknown_entry_errors(tmp_path: Path) -> None:
    p = _write(tmp_path, "app.py", "def a():\n    pass\n")
    result = runner.invoke(app, ["flow", str(p), "--entry", "nope"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_missing_file_errors(tmp_path: Path) -> None:
    result = runner.invoke(app, ["flow", str(tmp_path / "nope.py")])
    assert result.exit_code == 1
    assert "File not found" in result.output


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


def test_live_mode_no_trace_decorators_warns(tmp_path: Path) -> None:
    p = _write(tmp_path, "plain.py", """
def hello():
    pass

if __name__ == "__main__":
    hello()
""")
    result = runner.invoke(app, ["flow", str(p), "--live"])
    assert result.exit_code == 0
    assert "No traced calls recorded" in result.output


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
