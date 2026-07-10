"""Best-effort, AST-only data-validation schema extraction for the flow
viewer — detects Pydantic ``BaseModel``/``BaseSettings`` subclasses and
their fields without importing or executing the target project, matching
this package's static-analysis guarantee.

Limitations (same trade-off as ``static.py``'s call resolution): this can't
resolve dynamically-constructed models (``create_model(...)``), can't follow
multi-file/aliased inheritance without a real import, and only unparses
``Annotated[...]``/``Field(...)`` metadata as text rather than evaluating it.
For full accuracy you'd need to actually import the module — out of scope
here to keep this tool's "never executes your code" guarantee intact.
"""
from __future__ import annotations

import ast

_PYDANTIC_BASE_NAMES = {"BaseModel", "BaseSettings"}


def _base_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _is_required(value: ast.expr | None) -> bool:
    if value is None:
        return True
    # `Field(...)` — the Pydantic convention for "required, but with extra metadata".
    if isinstance(value, ast.Call) and _base_name(value.func) == "Field" and value.args:
        first = value.args[0]
        return isinstance(first, ast.Constant) and first.value is Ellipsis
    return False


def extract_pydantic_fields(tree: ast.Module, lineno: int) -> list[dict] | None:
    """If the class defined at ``lineno`` in ``tree`` looks like a Pydantic
    model (bases include ``BaseModel``/``BaseSettings``), return its
    annotated fields as ``[{"name", "type", "default", "required"}, ...]``.
    Returns ``None`` if no such class is found there."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.lineno == lineno:
            base_names = {_base_name(b) for b in node.bases}
            if not (base_names & _PYDANTIC_BASE_NAMES):
                return None
            fields = []
            for stmt in node.body:
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    fields.append({
                        "name": stmt.target.id,
                        "type": ast.unparse(stmt.annotation),
                        "default": ast.unparse(stmt.value) if stmt.value is not None else None,
                        "required": _is_required(stmt.value),
                    })
            return fields
    return None


__all__ = ["extract_pydantic_fields"]
