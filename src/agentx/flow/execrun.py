"""Shared execution helper for ``--live``/``--serve``.

A naive ``runpy.run_path(path, run_name="__main__")`` runs a file as a bare
script — if that file is actually part of a package (its directory has an
``__init__.py``) and uses relative imports (``from .config import X``), that
fails with ``ImportError: attempted relative import with no known parent
package``, because ``runpy.run_path`` never sets up ``__package__``.

The fix is the same thing ``python -m pkg.module`` does: find the package
root (walk up through ``__init__.py``-containing parent directories, mirroring
``agentx.flow.project``'s own module-name derivation), put it on ``sys.path``,
and run the file as a real module via ``runpy.run_module`` instead.
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path


def _package_root_and_module(path: Path) -> tuple[Path, str]:
    # Intentionally NOT stripped to just "pkg" when path is pkg/__init__.py:
    # runpy.run_module("pkg", ...) on a bare package raises
    # "ImportError: No module named pkg.__main__; 'pkg' is a package and
    # cannot be directly executed" (same as `python -m pkg` without a
    # __main__.py) — a total failure. Keeping the dotted name as
    # "pkg.__init__" instead runs correctly for the standard
    # `if __name__ == "__main__":` idiom every target script here uses (only
    # unconditional top-level code before that guard runs twice — once as a
    # side effect of importing the parent package, once as the actual
    # target — an accepted, harmless quirk of this rare direct-__init__.py
    # case, verified empirically before choosing this over the "cleaner"
    # looking but actually broken alternative).
    parts = [path.stem]
    cur = path.parent
    while (cur / "__init__.py").exists():
        parts.insert(0, cur.name)
        cur = cur.parent
    return cur, ".".join(parts)


def run_target(path: str | Path) -> None:
    """Execute ``path`` as ``__main__`` — as a module within its package if
    it's part of one (so relative imports resolve), else as a bare script
    (unchanged behavior for standalone files)."""
    p = Path(path).resolve()
    if not (p.parent / "__init__.py").exists():
        runpy.run_path(str(p), run_name="__main__")
        return
    root, dotted = _package_root_and_module(p)
    root_str = str(root)
    already_on_path = root_str in sys.path
    if not already_on_path:
        sys.path.insert(0, root_str)
    try:
        runpy.run_module(dotted, run_name="__main__", alter_sys=True)
    finally:
        if not already_on_path:
            try:
                sys.path.remove(root_str)
            except ValueError:
                pass


__all__ = ["run_target"]
