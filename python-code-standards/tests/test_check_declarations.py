"""Tests for the declaration checker.

Every exemption is a place where a bug produces silence rather than a failure,
so exemptions are asserted as explicitly as violations.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from skill.tools.check_declarations import Violation, check_source, main, read_source


def names(source: str) -> list[str]:
    """Return the names reported as violations, in source order."""
    violations: list[Violation] = check_source(Path("t.py"), source)
    return [violation.name for violation in violations]


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("x = 1", ["x"]),
        ("x: int = 1", []),
        ("x: int\nx = 1", []),
        ("for x in [1]:\n    pass", ["x"]),
        ("x: int\nfor x in [1]:\n    pass", []),
        ("for a, b in []:\n    pass", ["a", "b"]),
        ("a: int\nb: int\nfor a, b in []:\n    pass", []),
        ("for a, *rest in []:\n    pass", ["a", "rest"]),
        ("with open('f') as fh:\n    pass", ["fh"]),
        ("import io\nfh: io.TextIOWrapper\nwith open('f') as fh:\n    pass", []),
        ("a = b = 1", ["a", "b"]),
    ],
    ids=[
        "bare-assign",
        "annotated-assign",
        "declared-then-assigned",
        "loop-target",
        "declared-loop-target",
        "tuple-unpack",
        "declared-tuple-unpack",
        "starred-unpack",
        "with-target",
        "declared-with-target",
        "chained-assign",
    ],
)
def test_bindings_require_declaration(source: str, expected: list[str]) -> None:
    """Ordinary bindings are reported unless annotated first."""
    assert names(source) == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("match p:\n    case [first, *rest]:\n        pass", ["first", "rest"]),
        ("match p:\n    case {'k': mapped, **extra}:\n        pass", ["mapped", "extra"]),
        ("match p:\n    case Point(x=cx):\n        pass", ["cx"]),
        ("match p:\n    case other:\n        pass", ["other"]),
        ("match p:\n    case 1 | 2:\n        pass", []),
        ("cx: int\nmatch p:\n    case Point(x=cx):\n        pass", []),
    ],
    ids=["sequence", "mapping-rest", "class-keyword", "capture-all", "literal-or", "declared-capture"],
)
def test_match_captures_require_declaration(source: str, expected: list[str]) -> None:
    """Structural pattern captures are bindings and can be pre-declared."""
    assert names(source) == expected


@pytest.mark.parametrize(
    "source",
    [
        "squares = [n * n for n in range(3)]",
        "pairs = {k: v for k, v in []}",
        "gen = (n for n in range(3))",
        "try:\n    pass\nexcept ValueError as exc:\n    print(exc)",
        "if (found := 1) is not None:\n    print(found)",
        "import json",
        "from pathlib import Path",
        "def f() -> None:\n    pass",
        "class C:\n    pass",
        "def f(a: int, *args: int, **kw: int) -> None:\n    print(a, args, kw)",
        "def f() -> None:\n    global g\n    g = 1",
    ],
    ids=[
        "list-comp-target",
        "dict-comp-target",
        "genexp-target",
        "except-name",
        "walrus",
        "import",
        "import-from",
        "function-def",
        "class-def",
        "parameters",
        "global",
    ],
)
def test_exemptions_are_not_reported(source: str) -> None:
    """Forms the language cannot annotate stay exempt.

    The outer binding in each comprehension case is declared to isolate the
    target itself as the thing under test.
    """
    declared: str = "squares: list[int]\npairs: dict[int, int]\ngen: object\n" + source
    assert names(declared) == []


def test_nested_scope_does_not_leak_declarations() -> None:
    """A declaration inside a function does not license a module-level binding."""
    source: str = "def f() -> None:\n    x: int\n    x = 1\nx = 2"
    assert names(source) == ["x"]


def test_enclosing_declaration_satisfies_inner_scope() -> None:
    """A module-level declaration is visible to a nested function."""
    source: str = "x: int\ndef f() -> None:\n    x = 1"
    assert names(source) == []


def test_class_body_alias_requires_declaration() -> None:
    """Method aliases in a class body are bindings like any other."""
    source: str = "class C:\n    def a(self) -> None:\n        pass\n    b = a"
    assert names(source) == ["b"]


def test_violation_reports_position_and_renders() -> None:
    """A violation carries a navigable location."""
    violations: list[Violation] = check_source(Path("m.py"), "\nvalue = 1")
    assert len(violations) == 1
    assert violations[0].line == 2
    assert "value" in violations[0].render()


def test_reads_notebook_code_cells(tmp_path: Path) -> None:
    """Notebook code cells are concatenated; markdown and magics are skipped."""
    notebook: Path = tmp_path / "nb.ipynb"
    notebook.write_text(
        json.dumps(
            {
                "cells": [
                    {"cell_type": "code", "source": ["%matplotlib inline\n", "total: int = 0\n"]},
                    {"cell_type": "markdown", "source": ["prose"]},
                    {"cell_type": "code", "source": ["for row in []:\n", "    pass\n"]},
                ]
            }
        ),
        encoding="utf-8",
    )
    assert names(read_source(notebook)) == ["row"]


def test_main_returns_nonzero_on_violation(tmp_path: Path) -> None:
    """The CLI exits nonzero when anything is reported."""
    module: Path = tmp_path / "m.py"
    module.write_text("x = 1\n", encoding="utf-8")
    assert main([str(module)]) == 1


def test_main_returns_zero_when_clean(tmp_path: Path) -> None:
    """The CLI exits zero on conforming code."""
    module: Path = tmp_path / "m.py"
    module.write_text("x: int = 1\n", encoding="utf-8")
    assert main([str(module)]) == 0


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("async def f() -> None:\n    async for x in g():\n        pass", ["x"]),
        ("async def f() -> None:\n    x: int\n    async for x in g():\n        pass", []),
        ("async def f() -> None:\n    async with g() as h:\n        pass", ["h"]),
        ("async def f() -> None:\n    h: object\n    async with g() as h:\n        pass", []),
        ("async def f() -> None:\n    y = 1", ["y"]),
    ],
    ids=["async-for", "declared-async-for", "async-with", "declared-async-with", "async-body"],
)
def test_async_forms(source: str, expected: list[str]) -> None:
    """Async statements bind exactly like their synchronous counterparts."""
    assert names(source) == expected


def test_lambda_parameters_are_declared() -> None:
    """Lambda parameters count as declared within the lambda."""
    assert names("f: object\nf = lambda a: a") == []


def test_nonlocal_is_exempt() -> None:
    """A nonlocal name is managed by the enclosing scope."""
    source: str = "def outer() -> None:\n    v: int = 0\n    def inner() -> None:\n        nonlocal v\n        v = 1"
    assert names(source) == []


def test_augmented_assignment_is_not_a_first_binding() -> None:
    """``+=`` requires an existing binding, so it is not reported."""
    assert names("n: int = 0\nn += 1") == []


def test_read_source_accepts_string_cell_source(tmp_path: Path) -> None:
    """Notebook cells may store source as a single string."""
    notebook: Path = tmp_path / "nb.ipynb"
    notebook.write_text(json.dumps({"cells": [{"cell_type": "code", "source": "z = 1\n"}]}), encoding="utf-8")
    assert names(read_source(notebook)) == ["z"]


def test_main_walks_directories(tmp_path: Path) -> None:
    """A directory argument is searched for modules and notebooks."""
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("q = 1\n", encoding="utf-8")
    (tmp_path / "pkg" / "b.ipynb").write_text(json.dumps({"cells": [{"cell_type": "code", "source": "w = 1\n"}]}), encoding="utf-8")
    assert main([str(tmp_path)]) == 1


def test_main_reports_unparseable_source(tmp_path: Path) -> None:
    """A syntax error is reported rather than raised."""
    module: Path = tmp_path / "broken.py"
    module.write_text("def (:\n", encoding="utf-8")
    assert main([str(module)]) == 1


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("class C:\n    def __init__(self) -> None:\n        self.total = 0", ["self.total"]),
        ("class C:\n    total: int\n    def __init__(self) -> None:\n        self.total = 0", []),
        ("class C:\n    def __init__(self) -> None:\n        self.total: int = 0", []),
        ("class C:\n    def load(self) -> None:\n        self.cache = {}", ["self.cache"]),
        ("class C:\n    total: int\n    def f(self) -> None:\n        for self.total in []:\n            pass", []),
        ("class C:\n    def f(self) -> None:\n        for self.n in []:\n            pass", ["self.n"]),
        ("class C:\n    a: int\n    b: int\n    def f(self) -> None:\n        self.a, self.b = 1, 2", []),
        ("class C:\n    def f(cls) -> None:\n        cls.registry = {}", ["cls.registry"]),
        ("class C:\n    def f(self) -> None:\n        other.value = 1", []),
    ],
    ids=[
        "undeclared-in-init",
        "declared-in-class-body",
        "annotated-at-binding",
        "assigned-outside-init",
        "declared-attribute-loop-target",
        "undeclared-attribute-loop-target",
        "declared-tuple-targets",
        "non-self-receiver-still-checked",
        "other-object-attribute-ignored",
    ],
)
def test_instance_attributes_require_declaration(source: str, expected: list[str]) -> None:
    """Instance attributes are bindings and need a class-body annotation."""
    assert names(source) == expected


def test_dataclass_fields_satisfy_the_rule() -> None:
    """Dataclass fields are class-body annotations, so nothing extra is required."""
    source: str = "@dataclass\nclass V:\n    total: int\n    def bump(self) -> None:\n        self.total = 1"
    assert names(source) == []


def test_pydantic_model_fields_satisfy_the_rule() -> None:
    """Pydantic fields are class-body annotations for the same reason."""
    source: str = "class M(BaseModel):\n    name: str\n    def rename(self) -> None:\n        self.name = 'x'"
    assert names(source) == []


def test_inherited_declaration_satisfies_subclass() -> None:
    """An in-file base class's declarations cover the subclass."""
    source: str = "class P:\n    total: int\nclass C(P):\n    def reset(self) -> None:\n        self.total = 0"
    assert names(source) == []


def test_nested_function_receiver_is_not_confused() -> None:
    """A closure inside a method is not checked against the outer receiver."""
    source: str = "class C:\n    total: int\n    def f(self) -> None:\n        def inner(other: object) -> None:\n            other.total = 1"
    assert names(source) == []
