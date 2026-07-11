"""Tests for agentx.flow.gitmeta — per-node git blame recency/churn info."""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

from agentx.flow import gitmeta


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _init_repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "a@b.c")
    _git(tmp_path, "config", "user.name", "tester")
    return tmp_path


def test_blame_file_returns_none_outside_a_git_repo(tmp_path: Path) -> None:
    p = tmp_path / "app.py"
    p.write_text("def a():\n    pass\n", encoding="utf-8")
    assert gitmeta.blame_file(str(p)) is None


def test_blame_file_returns_none_for_untracked_file(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    p = tmp_path / "app.py"
    p.write_text("def a():\n    pass\n", encoding="utf-8")
    # Never `git add`+committed — untracked.
    assert gitmeta.blame_file(str(p)) is None


def test_node_git_info_tracks_last_change_and_churn_per_line_range(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    p = tmp_path / "app.py"
    p.write_text("def a():\n    pass\n\n\ndef b():\n    pass\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "c1")
    time.sleep(1.1)  # ensure a distinct author-time for the second commit
    p.write_text("def a():\n    return 1\n\n\ndef b():\n    pass\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "c2 touches only a()")

    cache: dict = {}
    info_a = gitmeta.node_git_info(str(p), 1, 2, cache)
    info_b = gitmeta.node_git_info(str(p), 5, 6, cache)

    assert info_a is not None and info_b is not None
    # a() was touched by both commits (churn=2); b() only by the first (churn=1).
    assert info_a["churn"] == 2
    assert info_b["churn"] == 1
    # a()'s last change is strictly newer than b()'s.
    assert info_a["last_change"] > info_b["last_change"]
    assert len(info_a["commit"]) == 8


def test_node_git_info_none_when_file_or_lineno_missing() -> None:
    assert gitmeta.node_git_info(None, 1, 2, {}) is None
    assert gitmeta.node_git_info("app.py", None, 2, {}) is None


def test_blame_cache_is_reused_across_calls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _init_repo(tmp_path)
    p = tmp_path / "app.py"
    p.write_text("def a():\n    pass\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "c1")

    calls = []
    real_run = subprocess.run

    def spy_run(*args, **kwargs):
        calls.append(args)
        return real_run(*args, **kwargs)

    monkeypatch.setattr(subprocess, "run", spy_run)
    cache: dict = {}
    gitmeta.node_git_info(str(p), 1, 2, cache)
    gitmeta.node_git_info(str(p), 1, 2, cache)
    blame_calls = [c for c in calls if "blame" in c[0]]
    assert len(blame_calls) == 1  # second lookup hit the cache, no new subprocess call
