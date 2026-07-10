"""Tests for agentx.scaffold.upgrade — `agentx upgrade`'s regenerate+diff plan."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from typer.testing import CliRunner

from agentx.cli import app
from agentx.scaffold import graphviz
from agentx.scaffold.spec import AgentSpec, ProjectSpec
from agentx.scaffold.generator import generate_project
from agentx.scaffold.upgrade import apply_upgrade, plan_upgrade

runner = CliRunner()


def _make_project(tmp_path: Path, **spec_kwargs) -> Path:
    spec = ProjectSpec(
        name="upgradebot", framework="langgraph", provider="openai",
        agents=[AgentSpec(name="assistant", role="Helper", goal="Help.", system_prompt="Be helpful.")],
        **spec_kwargs,
    )
    result = generate_project(spec, tmp_path / "upgradebot", overwrite=True)
    return result.target_dir


def test_fresh_project_has_no_diff(tmp_path: Path) -> None:
    root = _make_project(tmp_path)
    _root2, manifest = graphviz.load_manifest(root)
    staging, entries = plan_upgrade(root, manifest)
    try:
        assert entries == []
    finally:
        shutil.rmtree(staging.parent, ignore_errors=True)


def test_deleted_file_shows_as_new(tmp_path: Path) -> None:
    root = _make_project(tmp_path)
    (root / "tests" / "test_main.py").unlink()
    _root2, manifest = graphviz.load_manifest(root)
    staging, entries = plan_upgrade(root, manifest)
    try:
        assert any(e.status == "new" and e.relative_path == "tests/test_main.py" for e in entries)
    finally:
        shutil.rmtree(staging.parent, ignore_errors=True)


def test_hand_edited_file_shows_as_changed(tmp_path: Path) -> None:
    root = _make_project(tmp_path)
    readme = root / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8") + "\ncustom note\n", encoding="utf-8")
    _root2, manifest = graphviz.load_manifest(root)
    staging, entries = plan_upgrade(root, manifest)
    try:
        assert any(e.status == "changed" and e.relative_path == "README.md" for e in entries)
    finally:
        shutil.rmtree(staging.parent, ignore_errors=True)


def test_prompts_json_edit_is_protected_not_changed(tmp_path: Path) -> None:
    root = _make_project(tmp_path)
    prompts_path = root / "prompts.json"
    data = json.loads(prompts_path.read_text(encoding="utf-8"))
    data["agents"]["assistant"]["system_prompt"] = "A hand-tuned prompt via `agentx prompt set`."
    prompts_path.write_text(json.dumps(data), encoding="utf-8")
    _root2, manifest = graphviz.load_manifest(root)
    staging, entries = plan_upgrade(root, manifest)
    try:
        assert any(e.status == "protected" and e.relative_path == "prompts.json" for e in entries)
    finally:
        shutil.rmtree(staging.parent, ignore_errors=True)


def test_apply_writes_new_and_changed_but_skips_protected(tmp_path: Path) -> None:
    root = _make_project(tmp_path)
    (root / "tests" / "test_main.py").unlink()
    prompts_path = root / "prompts.json"
    data = json.loads(prompts_path.read_text(encoding="utf-8"))
    data["agents"]["assistant"]["system_prompt"] = "A hand-tuned prompt."
    prompts_path.write_text(json.dumps(data), encoding="utf-8")

    _root2, manifest = graphviz.load_manifest(root)
    staging, entries = plan_upgrade(root, manifest)
    try:
        written = apply_upgrade(root, staging, entries, force=False)
    finally:
        shutil.rmtree(staging.parent, ignore_errors=True)

    assert "tests/test_main.py" in written
    assert "prompts.json" not in written
    assert (root / "tests" / "test_main.py").exists()
    # The hand-tuned prompt survives untouched.
    assert json.loads(prompts_path.read_text())["agents"]["assistant"]["system_prompt"] == "A hand-tuned prompt."


def test_apply_with_force_writes_protected_files(tmp_path: Path) -> None:
    # Note: the spec used to regenerate prompts.json is itself reconstructed
    # FROM prompts.json (agent role/goal/system_prompt aren't stored anywhere
    # else) — so --force reformats/canonicalizes prompts.json but can't
    # "revert" a hand-edited prompt back to some earlier value; there's no
    # earlier value persisted anywhere to revert to. This just confirms the
    # file is written when --force is passed, not silently left alone.
    root = _make_project(tmp_path)
    prompts_path = root / "prompts.json"
    data = json.loads(prompts_path.read_text(encoding="utf-8"))
    data["agents"]["assistant"]["system_prompt"] = "A hand-tuned prompt."
    prompts_path.write_text(json.dumps(data), encoding="utf-8")  # unformatted, differs byte-for-byte

    _root2, manifest = graphviz.load_manifest(root)
    staging, entries = plan_upgrade(root, manifest)
    try:
        written = apply_upgrade(root, staging, entries, force=True)
    finally:
        shutil.rmtree(staging.parent, ignore_errors=True)

    assert "prompts.json" in written
    # Content is preserved (it was the reconstruction source) even though the
    # file was rewritten (canonical formatting now, not the raw json.dumps).
    assert json.loads(prompts_path.read_text())["agents"]["assistant"]["system_prompt"] == "A hand-tuned prompt."


def test_cli_dry_run_does_not_write(tmp_path: Path) -> None:
    root = _make_project(tmp_path)
    (root / "tests" / "test_main.py").unlink()
    result = runner.invoke(app, ["upgrade", "--project", str(root)])
    assert result.exit_code == 0
    assert "Dry run" in result.output
    assert not (root / "tests" / "test_main.py").exists()


def test_cli_apply_writes_changes(tmp_path: Path) -> None:
    root = _make_project(tmp_path)
    (root / "tests" / "test_main.py").unlink()
    result = runner.invoke(app, ["upgrade", "--project", str(root), "--apply"])
    assert result.exit_code == 0
    assert "Wrote" in result.output
    assert (root / "tests" / "test_main.py").exists()


def test_cli_up_to_date_reports_no_changes(tmp_path: Path) -> None:
    root = _make_project(tmp_path)
    result = runner.invoke(app, ["upgrade", "--project", str(root)])
    assert result.exit_code == 0
    assert "up to date" in result.output


def test_cli_missing_manifest_errors(tmp_path: Path) -> None:
    result = runner.invoke(app, ["upgrade", "--project", str(tmp_path)])
    assert result.exit_code == 1
    assert "No agentx.json found" in result.output
