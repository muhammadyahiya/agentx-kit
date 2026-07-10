"""Tests for agentx.flow.execrun — package-aware execution for --live/--serve."""
from __future__ import annotations

from pathlib import Path

import pytest

from agentx.flow.execrun import run_target


def _write(root: Path, rel: str, source: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(source, encoding="utf-8")
    return p


def test_relative_import_inside_a_package_resolves(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    # Package names must be unique across tests in this file — pytest runs
    # them all in one process, and Python caches imported package names in
    # `sys.modules`, so reusing a name would silently resolve to an earlier
    # test's cached module instead of this test's own tmp_path tree.
    _write(tmp_path, "pkg_flat/__init__.py", "")
    _write(tmp_path, "pkg_flat/config.py", "SETTING = 'hello'\n")
    target = _write(tmp_path, "pkg_flat/server.py", """
from .config import SETTING

if __name__ == "__main__":
    print("SETTING =", SETTING)
""")
    run_target(target)
    assert "SETTING = hello" in capsys.readouterr().out


def test_standalone_script_still_works(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    target = _write(tmp_path, "app.py", """
if __name__ == "__main__":
    print("plain script ran")
""")
    run_target(target)
    assert "plain script ran" in capsys.readouterr().out


def test_nested_package_relative_import_resolves(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    _write(tmp_path, "pkg_nested/__init__.py", "")
    _write(tmp_path, "pkg_nested/utils.py", "VALUE = 42\n")
    _write(tmp_path, "pkg_nested/sub/__init__.py", "")
    target = _write(tmp_path, "pkg_nested/sub/main.py", """
from ..utils import VALUE

if __name__ == "__main__":
    print("VALUE =", VALUE)
""")
    run_target(target)
    assert "VALUE = 42" in capsys.readouterr().out


def test_syspath_is_restored_after_running(tmp_path: Path) -> None:
    import sys

    _write(tmp_path, "pkg_syspath/__init__.py", "")
    target = _write(tmp_path, "pkg_syspath/server.py", "if __name__ == '__main__':\n    pass\n")
    before = list(sys.path)
    run_target(target)
    assert sys.path == before
