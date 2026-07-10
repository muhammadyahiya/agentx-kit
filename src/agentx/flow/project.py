"""Whole-project extension of :mod:`agentx.flow.static` — walks a directory of
Python files (instead of just one) and builds a single function-call
:class:`~agentx.flow.model.Flow` spanning the whole project: packages,
modules, classes, and functions/methods as nodes, with cross-file calls
resolved through each file's own ``import``/``from ... import`` statements.

Same trade-off as :mod:`agentx.flow.static`: everything here is ``ast``-based
(nothing is imported or executed), and call resolution is best-effort — a
call through a variable holding some instance (``agent.run()``) can't be
resolved without type inference and is left external, same as single-file
mode.
"""
from __future__ import annotations

import ast
import os
from pathlib import Path

from .model import Flow
from .static import _CallCollector, _subgraph_from

_EXCLUDED_DIRS = {
    ".git", ".venv", "venv", "__pycache__", ".tox",
    ".mypy_cache", ".pytest_cache", "node_modules", "build", "dist",
}


def _is_excluded_dir(name: str) -> bool:
    return name in _EXCLUDED_DIRS or name.startswith(".") or name.endswith(".egg-info")


def _iter_python_files(root: Path, *, include_tests: bool) -> list[Path]:
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not _is_excluded_dir(d)]
        for fname in filenames:
            if not fname.endswith(".py"):
                continue
            if not include_tests and (fname.startswith("test_") or fname.endswith("_test.py")):
                continue
            path = Path(dirpath) / fname
            if not include_tests and "tests" in path.relative_to(root).parts[:-1]:
                continue
            files.append(path)
    return sorted(files)


def _module_name(path: Path, root: Path) -> tuple[str, bool]:
    """Dotted module name for ``path`` relative to ``root``, and whether it's a package ``__init__.py``."""
    parts = list(path.relative_to(root).parts)
    is_init = parts[-1] == "__init__.py"
    parts[-1] = parts[-1][: -len(".py")]
    if is_init:
        parts = parts[:-1]   # __init__.py's module name IS its own package dir
    return ".".join(parts), is_init


def _ancestors(dotted: str) -> list[str]:
    """Dotted names of every proper ancestor package of ``dotted``, root-to-leaf."""
    parts = dotted.split(".")
    return [".".join(parts[:i]) for i in range(1, len(parts))]


def _ensure_package_chain(flow: Flow, dotted: str) -> None:
    for anc in _ancestors(dotted):
        if anc not in flow.nodes:
            parent = anc.rsplit(".", 1)[0] if "." in anc else None
            flow.add_node(anc, kind="package", parent=parent)


class _ProjectCollector(ast.NodeVisitor):
    """Pass 1: register every class/function/method def in one file, module-qualified."""

    def __init__(self, module_dotted: str) -> None:
        self.module_dotted = module_dotted
        self.items: dict[str, tuple[ast.AST, str]] = {}   # qual -> (ast node, kind)
        self.parents: dict[str, str] = {}                  # qual -> parent qual
        self._scope: list[str] = []

    def _qual(self, name: str) -> str:
        return ".".join([self.module_dotted, *self._scope, name])

    def _parent_qual(self) -> str:
        return ".".join([self.module_dotted, *self._scope]) if self._scope else self.module_dotted

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        qual = self._qual(node.name)
        self.items[qual] = (node, "class")
        self.parents[qual] = self._parent_qual()
        self._scope.append(node.name)
        self.generic_visit(node)
        self._scope.pop()

    def _visit_func(self, node) -> None:
        qual = self._qual(node.name)
        self.items[qual] = (node, "function")
        self.parents[qual] = self._parent_qual()
        self._scope.append(node.name)
        self.generic_visit(node)
        self._scope.pop()

    visit_FunctionDef = _visit_func
    visit_AsyncFunctionDef = _visit_func


class _ImportCollector(ast.NodeVisitor):
    """Collect ``local name -> absolute dotted target`` for one file's imports."""

    def __init__(self, module_dotted: str, is_init: bool) -> None:
        self.module_dotted = module_dotted
        self.is_init = is_init
        self.map: dict[str, str] = {}

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.asname:
                self.map[alias.asname] = alias.name
            else:
                # `import a.b.c` binds the top-level name `a`; attribute access
                # on it reconstructs the rest, so map the root to itself.
                self.map[alias.name.split(".")[0]] = alias.name.split(".")[0]

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        base = self._resolve_base(node)
        for alias in node.names:
            if alias.name == "*":
                continue
            local = alias.asname or alias.name
            self.map[local] = f"{base}.{alias.name}" if base else alias.name

    def _resolve_base(self, node: ast.ImportFrom) -> str:
        if node.level == 0:
            return node.module or ""
        own_package = self.module_dotted if self.is_init else (
            self.module_dotted.rsplit(".", 1)[0] if "." in self.module_dotted else ""
        )
        parts = own_package.split(".") if own_package else []
        climb = node.level - 1
        base_parts = parts[: len(parts) - climb] if climb <= len(parts) else []
        base = ".".join(base_parts)
        if node.module:
            base = f"{base}.{node.module}" if base else node.module
        return base


def _resolve_project_call(called: str, *, bare_to_qual: dict[str, str], import_map: dict[str, str]) -> str | None:
    """Best-effort cross-file resolution: same-file bare name / ``self./cls.``
    method (mirrors ``static._resolve``'s exact behavior), else an imported
    symbol's absolute dotted target (validated against known nodes by the caller)."""
    if "." not in called:
        # same-file def wins over an import of the same bare name.
        return bare_to_qual.get(called) or import_map.get(called)
    rprefix, _, bare = called.rpartition(".")
    if rprefix in ("self", "cls"):
        return bare_to_qual.get(bare)
    root, _, rest = called.partition(".")
    if root in import_map:
        target = import_map[root]
        return f"{target}.{rest}" if rest else target
    return None


def build_project_flow(
    root: str | Path,
    *,
    entry: str | None = None,
    include_external: bool = True,
    include_tests: bool = True,
) -> Flow:
    """Build a project-wide call-graph :class:`~agentx.flow.model.Flow` for every
    ``.py`` file under ``root`` (packages/modules/classes/functions as nodes).

    Args:
        root: Directory to walk.
        entry: If given, return only the subgraph reachable from this function
            (bare or fully module-qualified name). Raises ``ValueError`` if not found.
        include_external: Include edges to calls that don't resolve to a
            function/class defined somewhere in the project.
        include_tests: Include ``test_*.py``/``*_test.py`` files and any
            ``tests/`` directory (on by default — they're real call edges too).
    """
    root = Path(root).resolve()
    files = _iter_python_files(root, include_tests=include_tests)

    records: list[tuple[Path, ast.Module, str, bool]] = []
    for path in files:
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            continue
        module_dotted, is_init = _module_name(path, root)
        if not module_dotted:
            module_dotted = root.name or "__root__"
        records.append((path, tree, module_dotted, is_init))

    flow = Flow(kind="static", scope="project")

    per_file: dict[Path, tuple[_ProjectCollector, dict[str, str], dict[str, str]]] = {}
    for path, tree, module_dotted, is_init in records:
        parent = module_dotted.rsplit(".", 1)[0] if "." in module_dotted else None
        _ensure_package_chain(flow, module_dotted)
        flow.add_node(module_dotted, file=str(path), lineno=1, kind="package" if is_init else "module", parent=parent)

        collector = _ProjectCollector(module_dotted)
        collector.visit(tree)
        for qual, (node_ast, kind_) in collector.items.items():
            flow.add_node(
                qual, file=str(path), lineno=getattr(node_ast, "lineno", None),
                kind=kind_, module=module_dotted, parent=collector.parents[qual],
            )

        bare_to_qual: dict[str, str] = {}
        for qual, (_, kind_) in collector.items.items():
            if kind_ == "function":
                bare_to_qual.setdefault(qual.rsplit(".", 1)[-1], qual)

        importer = _ImportCollector(module_dotted, is_init)
        importer.visit(tree)
        per_file[path] = (collector, bare_to_qual, importer.map)

    for path, tree, module_dotted, is_init in records:
        collector, bare_to_qual, import_map = per_file[path]

        for qual, (node_ast, kind_) in collector.items.items():
            if kind_ != "function":
                continue
            calls = _CallCollector()
            for stmt in node_ast.body:
                calls.visit(stmt)
            for called in calls.calls:
                resolved = _resolve_project_call(called, bare_to_qual=bare_to_qual, import_map=import_map)
                if resolved and resolved in flow.nodes:
                    flow.add_edge(qual, resolved)
                elif include_external:
                    flow.add_node(called, external=True, kind="external")
                    flow.add_edge(qual, called)

        # Module-level calls (executed at import time) — attribute to the module node.
        module_calls = _CallCollector()
        for stmt in tree.body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            module_calls.visit(stmt)
        for called in module_calls.calls:
            resolved = _resolve_project_call(called, bare_to_qual=bare_to_qual, import_map=import_map)
            if resolved and resolved in flow.nodes:
                flow.add_edge(module_dotted, resolved)
            elif include_external:
                flow.add_node(called, external=True, kind="external")
                flow.add_edge(module_dotted, called)

    if entry:
        target = entry if entry in flow.nodes else None
        if target is None:
            global_bare_to_qual: dict[str, str] = {}
            for name, node in flow.nodes.items():
                if node.kind in ("function", "class"):
                    global_bare_to_qual.setdefault(name.rsplit(".", 1)[-1], name)
            target = global_bare_to_qual.get(entry)
        if target is None:
            raise ValueError(f"Function {entry!r} not found in {root}")
        sub = _subgraph_from(flow, target)
        sub.scope = "project"
        return sub

    return flow


__all__ = ["build_project_flow"]
