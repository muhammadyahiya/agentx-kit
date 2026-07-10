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
import warnings
from pathlib import Path

from ._ast_helpers import CallCollector, subgraph_from
from .model import Flow

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
        self.has_star_import = False

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
                # Can't resolve statically what names this introduces — any
                # call through one of them will fall through to "external"
                # rather than resolving to the real project node. Surfaced as
                # a warning (not silently dropped) so that's discoverable.
                self.has_star_import = True
                warnings.warn(
                    f"{self.module_dotted}: 'from {node.module or '.'} import *' can't be "
                    "resolved statically — calls through names it introduces will show as "
                    "external in the flow graph.",
                    stacklevel=2,
                )
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


def _module_dependency(target: str, project_modules: set[str], own_module: str) -> str | None:
    """Longest prefix of an import target that's a known project module —
    used to build the module-level dependency graph for cycle detection."""
    parts = target.split(".")
    for i in range(len(parts), 0, -1):
        candidate = ".".join(parts[:i])
        if candidate in project_modules and candidate != own_module:
            return candidate
    return None


def _detect_import_cycles(module_imports: dict[str, set[str]]) -> list[list[str]]:
    """DFS cycle detection over the project's module import graph. Returns one
    representative cycle (module names, first repeated at the end) per back
    edge found — not exhaustive for every cycle in a strongly-connected
    component, but enough to flag the problem."""
    white, gray, black = 0, 1, 2
    color = dict.fromkeys(module_imports, white)
    stack: list[str] = []
    cycles: list[list[str]] = []

    def dfs(node: str) -> None:
        color[node] = gray
        stack.append(node)
        for neighbor in module_imports.get(node, ()):
            if neighbor not in color:
                continue
            if color[neighbor] == gray:
                idx = stack.index(neighbor)
                cycles.append([*stack[idx:], neighbor])
            elif color[neighbor] == white:
                dfs(neighbor)
        stack.pop()
        color[node] = black

    for node in list(module_imports):
        if color[node] == white:
            dfs(node)
    return cycles


def build_project_flow(
    root: str | Path,
    *,
    entry: str | None = None,
    include_external: bool = True,
    include_tests: bool = True,
    max_files: int | None = None,
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
        max_files: If given and the number of discovered ``.py`` files exceeds
            it, raise ``ValueError`` instead of building a graph — a guard
            against accidentally pointing at a huge/unrelated directory (e.g.
            a home directory) with no feedback until it's already scanned
            everything.
    """
    root = Path(root).resolve()
    files = _iter_python_files(root, include_tests=include_tests)
    if max_files is not None and len(files) > max_files:
        raise ValueError(
            f"{len(files)} Python files found under {root} (max_files={max_files}). "
            "Pass a higher --max-files, or point at a smaller directory."
        )

    flow = Flow(kind="static", scope="project")

    # Pass 1: parse each file once, register every node + its own import map,
    # then let the parsed tree fall out of scope — pass 2 re-parses from disk
    # instead of keeping every file's AST resident simultaneously for the
    # whole function call, so peak memory no longer scales with project size
    # (at the cost of parsing each file twice; a deliberate CPU/memory trade
    # for large projects).
    per_file: dict[Path, tuple[dict[str, str], dict[str, str], str, bool]] = {}
    # per_file[path] = (bare_to_qual, import_map, module_dotted, is_init)

    for path in files:
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            # Unreadable (permissions) or not-actually-UTF-8-text (binary file
            # with a .py extension) — skip it rather than aborting the whole
            # project walk over one bad file.
            continue
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            continue

        module_dotted, is_init = _module_name(path, root)
        if not module_dotted:
            module_dotted = root.name or "__root__"

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

        per_file[path] = (bare_to_qual, importer.map, module_dotted, is_init)
        # `tree`/`collector`/`importer` fall out of scope here — nothing from
        # this file's AST is retained past this iteration.

    project_modules = {module_dotted for _, _, module_dotted, _ in per_file.values()}
    module_imports: dict[str, set[str]] = {}
    for _bare_to_qual, import_map, module_dotted, _is_init in per_file.values():
        deps = {
            dep for target in import_map.values()
            if (dep := _module_dependency(target, project_modules, module_dotted)) is not None
        }
        module_imports.setdefault(module_dotted, set()).update(deps)
    for cycle in _detect_import_cycles(module_imports):
        warnings.warn(f"Circular import detected: {' -> '.join(cycle)}", stacklevel=2)

    # Pass 2: re-parse each file (now that every project-wide node is known)
    # to resolve cross-file calls into edges.
    for path, (bare_to_qual, import_map, module_dotted, _is_init) in per_file.items():
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue  # file changed on disk between passes — skip rather than crash

        collector = _ProjectCollector(module_dotted)
        collector.visit(tree)

        for qual, (node_ast, kind_) in collector.items.items():
            if kind_ != "function":
                continue
            calls = CallCollector()
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
        module_calls = CallCollector()
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
        sub = subgraph_from(flow, target)
        sub.scope = "project"
        return sub

    return flow


__all__ = ["build_project_flow"]
