"""Tests for agentx.scaffold.validate — agentx.json structural validation
(``agentx validate``)."""
from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from agentx.cli import app
from agentx.scaffold.validate import validate_manifest

runner = CliRunner()


def _base_manifest(**overrides) -> dict:
    manifest = {
        "manifest_version": 1,
        "name": "test-bot",
        "framework": "langgraph",
        "provider": "openai",
        "model": "gpt-4o-mini",
        "agents": ["assistant"],
        "orchestration": "supervisor",
        "features": {
            "agent_mode": "chat",
            "memory": "none",
            "mcp": False,
            "mcp_tools": [],
        },
        "extras": ["openai"],
    }
    manifest.update(overrides)
    return manifest


def test_valid_manifest_has_no_findings(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("agentx-kit[openai]\n", encoding="utf-8")
    (tmp_path / ".env.example").write_text("", encoding="utf-8")
    findings = validate_manifest(tmp_path, _base_manifest())
    assert findings == []


def test_missing_required_keys_reported(tmp_path: Path) -> None:
    findings = validate_manifest(tmp_path, {})
    messages = [f.message for f in findings]
    assert any("name" in m for m in messages)
    assert any("framework" in m for m in messages)
    assert any(f.level == "error" for f in findings)


def test_unknown_framework_is_an_error(tmp_path: Path) -> None:
    findings = validate_manifest(tmp_path, _base_manifest(framework="flask"))
    assert any(f.level == "error" and "framework" in f.message for f in findings)


def test_unknown_provider_is_an_error(tmp_path: Path) -> None:
    findings = validate_manifest(tmp_path, _base_manifest(provider="not-a-real-provider"))
    assert any(f.level == "error" and "provider" in f.message for f in findings)


def test_empty_agents_list_is_a_warning(tmp_path: Path) -> None:
    findings = validate_manifest(tmp_path, _base_manifest(agents=[]))
    assert any(f.level == "warning" and "agents" in f.message for f in findings)


def test_unknown_mcp_tool_is_an_error(tmp_path: Path) -> None:
    manifest = _base_manifest()
    manifest["features"]["mcp"] = True
    manifest["features"]["mcp_tools"] = ["not_a_real_tool"]
    findings = validate_manifest(tmp_path, manifest)
    assert any(f.level == "error" and "mcp_tools" in f.message for f in findings)


def test_missing_pyproject_is_a_warning(tmp_path: Path) -> None:
    findings = validate_manifest(tmp_path, _base_manifest())
    assert any("pyproject.toml" in f.message for f in findings)


def test_prompts_json_agent_mismatch_is_a_warning(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("agentx-kit[openai]\n", encoding="utf-8")
    (tmp_path / ".env.example").write_text("", encoding="utf-8")
    (tmp_path / "prompts.json").write_text(json.dumps({"agents": {}}), encoding="utf-8")
    findings = validate_manifest(tmp_path, _base_manifest(agents=["assistant"]))
    assert any("prompts.json" in f.message for f in findings)


def test_invalid_prompts_json_is_an_error(tmp_path: Path) -> None:
    (tmp_path / "prompts.json").write_text("{not valid json", encoding="utf-8")
    findings = validate_manifest(tmp_path, _base_manifest())
    assert any(f.level == "error" and "prompts.json" in f.message for f in findings)


def test_cli_validate_clean_project_exits_0(tmp_path: Path) -> None:
    (tmp_path / "agentx.json").write_text(json.dumps(_base_manifest()), encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("agentx-kit[openai]\n", encoding="utf-8")
    (tmp_path / ".env.example").write_text("", encoding="utf-8")
    result = runner.invoke(app, ["validate", "--project", str(tmp_path)])
    assert result.exit_code == 0
    assert "looks valid" in result.output


def test_cli_validate_broken_project_exits_1(tmp_path: Path) -> None:
    (tmp_path / "agentx.json").write_text(
        json.dumps(_base_manifest(framework="flask", provider="not-real")), encoding="utf-8",
    )
    result = runner.invoke(app, ["validate", "--project", str(tmp_path)])
    assert result.exit_code == 1
    assert "error(s)" in result.output


def test_cli_validate_missing_manifest_exits_1(tmp_path: Path) -> None:
    result = runner.invoke(app, ["validate", "--project", str(tmp_path)])
    assert result.exit_code == 1
    assert "No agentx.json found" in result.output
