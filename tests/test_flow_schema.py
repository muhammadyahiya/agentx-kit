"""Tests for agentx.flow.schema — AST-only Pydantic field extraction."""
from __future__ import annotations

import ast

from agentx.flow.schema import extract_pydantic_fields


def _class_lineno(tree: ast.Module) -> int:
    return next(n.lineno for n in ast.walk(tree) if isinstance(n, ast.ClassDef))


def test_extracts_fields_with_types_and_defaults() -> None:
    tree = ast.parse("""
from pydantic import BaseModel, Field

class User(BaseModel):
    name: str
    age: int = 0
    email: str = Field(...)
    nickname: str | None = None
""")
    fields = extract_pydantic_fields(tree, _class_lineno(tree))
    by_name = {f["name"]: f for f in fields}
    assert by_name["name"] == {"name": "name", "type": "str", "default": None, "required": True}
    assert by_name["age"]["default"] == "0"
    assert by_name["age"]["required"] is False
    assert by_name["email"]["required"] is True  # Field(...) => required
    assert by_name["nickname"]["type"] == "str | None"


def test_non_pydantic_class_returns_none() -> None:
    tree = ast.parse("""
class Plain:
    x: int
""")
    assert extract_pydantic_fields(tree, _class_lineno(tree)) is None


def test_basesettings_also_detected() -> None:
    tree = ast.parse("""
from pydantic_settings import BaseSettings

class Config(BaseSettings):
    debug: bool = False
""")
    fields = extract_pydantic_fields(tree, _class_lineno(tree))
    assert fields == [{"name": "debug", "type": "bool", "default": "False", "required": False}]


def test_no_class_at_lineno_returns_none() -> None:
    tree = ast.parse("def f():\n    pass\n")
    assert extract_pydantic_fields(tree, 1) is None


def test_class_with_no_annotated_fields_returns_empty_list() -> None:
    tree = ast.parse("""
from pydantic import BaseModel

class Empty(BaseModel):
    pass
""")
    assert extract_pydantic_fields(tree, _class_lineno(tree)) == []
