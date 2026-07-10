"""CLI-level tests for `agentx new`'s discoverability/output flags —
--list-frameworks, --list-providers, --quiet, --json."""
from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from agentx.cli import app

runner = CliRunner()


def test_list_frameworks_prints_choices_and_exits_0() -> None:
    result = runner.invoke(app, ["new", "--list-frameworks"])
    assert result.exit_code == 0
    assert "langgraph" in result.output
    assert "crewai" in result.output


def test_list_providers_prints_known_ids_and_exits_0() -> None:
    result = runner.invoke(app, ["new", "--list-providers"])
    assert result.exit_code == 0
    assert "openai" in result.output
    assert "anthropic" in result.output


def test_json_flag_prints_machine_readable_summary(tmp_path: Path) -> None:
    target = tmp_path / "jsonbot"
    result = runner.invoke(app, ["new", "--name", "jsonbot", "--yes", "--out", str(target), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["ok"] is True
    assert data["name"] == "jsonbot"
    assert data["target_dir"] == str(target)
    assert any(f.endswith("agentx.json") for f in data["files"])


def test_json_flag_reports_failure_as_json(tmp_path: Path) -> None:
    target = tmp_path / "existing"
    target.mkdir()
    (target / "keep.txt").write_text("hi", encoding="utf-8")
    result = runner.invoke(app, ["new", "--name", "x", "--yes", "--out", str(target), "--json"])
    assert result.exit_code == 1
    data = json.loads(result.output)
    assert data["ok"] is False
    assert "error" in data


def test_quiet_flag_suppresses_result_panel(tmp_path: Path) -> None:
    target = tmp_path / "quietbot"
    result = runner.invoke(app, ["new", "--name", "quietbot", "--yes", "--out", str(target), "--quiet"])
    assert result.exit_code == 0
    assert result.output.strip() == ""
    assert target.exists()
