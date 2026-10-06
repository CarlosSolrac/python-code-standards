"""Tests for the declaration checker.

Every exemption is a place where a bug produces silence rather than a failure,
so exemptions are asserted as explicitly as violations.
"""

from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path

import pytest

from skill.tools.check_declarations import Violation, check_source, iter_python_files, load_enum_bases, main, package_of, read_source


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


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("match p:\n    case (1 | 2) as pair:\n        pass", ["pair"]),
        ("match p:\n    case _:\n        pass", []),
        ("match p:\n    case [1, *_]:\n        pass", []),
        ("match p:\n    case {'k': v}:\n        pass", ["v"]),
        ("match p:\n    case n if n > 0:\n        pass", ["n"]),
    ],
    ids=["as-pattern", "wildcard", "anonymous-star", "mapping-without-rest", "guarded-capture"],
)
def test_match_pattern_variants(source: str, expected: list[str]) -> None:
    """Patterns that bind nothing stay silent; wrapped and guarded captures are still reported."""
    assert names(source) == expected


@pytest.mark.parametrize(
    "source",
    [
        "with open('f'):\n    pass",
        "try:\n    pass\nexcept ValueError:\n    pass",
        "evens: set[int]\nevens = {n for n in range(3)}",
    ],
    ids=["with-without-as", "except-without-name", "set-comp-target"],
)
def test_forms_without_bindings_are_not_reported(source: str) -> None:
    """Statements that bind no annotatable name produce no violation."""
    assert names(source) == []


def test_dotted_base_class_contributes_no_declarations() -> None:
    """Only in-file bases named directly are resolved; a dotted base declares nothing."""
    source: str = "class C(models.Base):\n    def reset(self) -> None:\n        self.total = 0"
    assert names(source) == ["self.total"]


def test_local_annotation_in_method_is_not_an_attribute() -> None:
    """An annotated local inside a method neither reports nor declares an attribute."""
    source: str = "class C:\n    def f(self) -> None:\n        n: int = 0\n        self.n = n"
    assert names(source) == ["self.n"]


def test_read_source_ignores_malformed_cells(tmp_path: Path) -> None:
    """A notebook whose ``cells`` is not a list yields no source rather than raising."""
    notebook: Path = tmp_path / "nb.ipynb"
    notebook.write_text(json.dumps({"cells": {"cell_type": "code"}}), encoding="utf-8")
    assert read_source(notebook) == ""


def test_runs_as_script(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Executed as a script, the module exits with ``main``'s status."""
    module: Path = tmp_path / "m.py"
    module.write_text("x: int = 1\n", encoding="utf-8")
    script: Path = Path(__file__).parent.parent / "skill" / "tools" / "check_declarations.py"
    monkeypatch.setattr(sys, "argv", [str(script), str(module)])
    exit_info: pytest.ExceptionInfo[SystemExit]
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_path(str(script), run_name="__main__")
    assert exit_info.value.code == 0


def test_comprehension_variable_does_not_declare_the_outer_name() -> None:
    """Comprehension targets live in their own scope; a later binding of that name is still undeclared."""
    assert names("rows: list[int] = []\n[x for x in rows]\nx = 1") == ["x"]


def test_violation_reports_path_line_and_column() -> None:
    source: str = "def f(a: int) -> None:\n    b = a\n\n\nclass C:\n    def __init__(self) -> None:\n        self.v = 1\n"
    rendered: list[str] = [violation.render() for violation in check_source(Path("m.py"), source)]
    assert rendered == ["m.py:2:4: b bound before annotation", "m.py:7:8: self.v bound before annotation"]


@pytest.mark.parametrize(
    "source",
    [
        "import os.path\nos = 1",
        "import numpy as np\nnp = 1",
        "from a import b as c\nc = 1",
        "from a import b\nb = 1",
        "try:\n    pass\nexcept ValueError as e:\n    e = 1",
        "(y := 1)\ny = 2",
        "def f() -> None:\n    pass\nf = 1",
        "async def g() -> None:\n    pass\ng = 1",
        "class K:\n    pass\nK = 1",
        "def f(a: int, *args: int, **kw: int) -> None:\n    a = 1\n    args = (2,)\n    kw = {}",
        "__all__ = ['x']",
    ],
    ids=["import-dotted", "import-as", "from-import-as", "from-import", "except-as", "walrus", "def", "async-def", "class", "parameters", "dunder"],
)
def test_names_declared_by_other_constructs_stay_declared(source: str) -> None:
    assert names(source) == []


def test_a_name_is_reported_once() -> None:
    assert names("x = 1\nx = 2") == ["x"]


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("class C:\n    def __init__(self) -> None:\n        self.total: int = 0\n        self.total = 1", []),
        ("class C:\n    def m(self, other: 'C') -> None:\n        other.x: int = 1\n        self.x = 2", ["self.x"]),
        ("class C:\n    def __init__(self) -> None:\n        self.a, self.b = 1, 2", ["self.a", "self.b"]),
        ("class C:\n    def __init__(self) -> None:\n        self.y = 1\n        self.y = 2", ["self.y"]),
        ("class A:\n    a: int\n\nclass B:\n    b: int\n\nclass C(A, B):\n    def __init__(self) -> None:\n        self.a = 1\n        self.b = 2", []),
        ("class A:\n    x: int\n\nclass Outer:\n    class Inner(A):\n        def __init__(self) -> None:\n            self.x = 1", []),
    ],
    ids=["annotated-in-method", "other-receiver", "tuple-target", "reported-once", "two-bases", "nested-class-base"],
)
def test_instance_attribute_declarations(source: str, expected: list[str]) -> None:
    assert names(source) == expected


def test_match_as_binds_its_subpattern_and_name() -> None:
    """``whole`` is reported at the pattern's start, the ``[``, so it sorts before ``a``."""
    assert names("v: object = []\nmatch v:\n    case [a] as whole:\n        pass") == ["whole", "a"]


def test_mapping_rest_is_reported_at_the_closing_line() -> None:
    source: str = "v: object = {}\nmatch v:\n    case {\n        'k': 1,\n        **rest\n    }:\n        pass\n"
    violations: list[Violation] = check_source(Path("m.py"), source)
    assert [(violation.name, violation.line) for violation in violations] == [("rest", 6)]


def test_read_source_keeps_only_code_cells_without_magics(tmp_path: Path) -> None:
    notebook: Path = tmp_path / "n.ipynb"
    cells: list[dict[str, object]] = [
        {"cell_type": "markdown", "source": ["x = 1"]},
        {"cell_type": "code", "source": ["  %time f()\n", "!pip install duckdb\n", "y: int = 2\n"]},
    ]
    notebook.write_text(json.dumps({"cells": cells}), encoding="utf-8")
    assert read_source(notebook) == "y: int = 2"


def test_iter_python_files_finds_modules_and_notebooks(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("", encoding="utf-8")
    (tmp_path / "b.ipynb").write_text("{}", encoding="utf-8")
    (tmp_path / "c.txt").write_text("", encoding="utf-8")
    assert [path.name for path in iter_python_files([tmp_path])] == ["a.py", "b.ipynb"]


def test_main_prints_violations_and_count(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    module: Path = tmp_path / "m.py"
    module.write_text("x = 1\ny = 2\n", encoding="utf-8")
    assert main([str(module)]) == 1
    out: str
    err: str
    out, err = capsys.readouterr()
    assert out.splitlines() == [f"{module}:1:0: x bound before annotation", f"{module}:2:0: y bound before annotation"]
    assert err == "\n2 declaration violation(s)\n"


def test_main_reports_a_file_it_cannot_parse(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    module: Path = tmp_path / "bad.py"
    module.write_text("def (:\n", encoding="utf-8")
    assert main([str(module)]) == 1
    out: str
    err: str
    out, err = capsys.readouterr()
    assert out == ""
    assert err.startswith(f"{module}:1:")
    assert ": could not parse: " in err


def test_help_shows_the_module_docstring(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("COLUMNS", "200")
    exit_info: pytest.ExceptionInfo[SystemExit]
    with pytest.raises(SystemExit) as exit_info:
        main(["--help"])
    assert exit_info.value.code == 0
    assert "Enforce the house rule that every variable is annotated before its first binding." in capsys.readouterr().out


def test_class_body_violation_reports_the_path() -> None:
    rendered: list[str] = [violation.render() for violation in check_source(Path("m.py"), "class C:\n    alias = int\n")]
    assert rendered == ["m.py:2:4: alias bound before annotation"]


def test_read_source_treats_a_cell_without_source_as_empty(tmp_path: Path) -> None:
    notebook: Path = tmp_path / "n.ipynb"
    notebook.write_text(json.dumps({"cells": [{"cell_type": "code"}]}), encoding="utf-8")
    assert read_source(notebook) == ""


@pytest.mark.parametrize(
    ("header", "base"),
    [
        ("from enum import Enum", "Enum"),
        ("from enum import IntEnum", "IntEnum"),
        ("from enum import StrEnum", "StrEnum"),
        ("from enum import Flag", "Flag"),
        ("from enum import IntFlag", "IntFlag"),
        ("from enum import ReprEnum", "ReprEnum"),
        ("from enum import Enum as E", "E"),
        ("import enum", "enum.Enum"),
        ("import enum as e", "e.Flag"),
    ],
)
def test_enum_members_are_exempt(header: str, base: str) -> None:
    """The typing spec forbids annotating enum members, so a plain assignment in an enum body is exempt."""
    assert names(f"{header}\nclass M({base}):\n    A = 1\n    B = auto()") == []


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("from enum import Enum\nclass B(Enum):\n    pass\nclass E(B):\n    A = 1", []),
        ("from enum import Enum\nclass B(Enum):\n    pass\nclass O:\n    class E(B):\n        A = 1", []),
        ("from enum import Enum\nclass B(Enum):\n    pass\ndef f() -> None:\n    class E(B):\n        A = 1", []),
        ("import enum\nclass O:\n    class E(enum.Enum):\n        A = 1", []),
        ("import enum\ndef f() -> None:\n    class E(enum.Enum):\n        A = 1", []),
        ("class C(Base):\n    A = 1", ["A"]),
        ("class C(Generic[T]):\n    A = 1", ["A"]),
        ("class C(Enum):\n    A = 1", ["A"]),
        ("from enum import auto\nclass C(auto):\n    A = 1", ["A"]),
        ("from .enum import Enum\nclass C(Enum):\n    A = 1", ["A"]),
        ("import enum\nclass C(enum.EnumType):\n    A = 1", ["A"]),
        ("import mylib\nclass C(mylib.Enum):\n    A = 1", ["A"]),
        ("from enum import Enum\nclass Base(Enum):\n    pass\nclass C(ns.Base):\n    A = 1", ["A"]),
        ("from enum import Flag\nclass Flag:\n    pass\nclass C(Flag):\n    A = 1", ["A"]),
        ("from enum import Flag\nfrom mylib import Flag\nclass C(Flag):\n    A = 1", ["A"]),
        ("import enum\nimport mylib as enum\nclass C(enum.Enum):\n    A = 1", ["A"]),
        ("from enum import Enum\nclass E(Enum):\n    A, (B, C) = 1, (2, 3)", []),
        ("from enum import Enum\nclass E(Enum):\n    A, *B = 1, 2", ["A", "B"]),
        ("from enum import Enum\nclass E(Enum):\n    A = 1\n    def f(self) -> None:\n        label = 1", ["label"]),
        ("from enum import Enum\ndef f() -> None:\n    class B(Enum):\n        pass\nclass E(B):\n    A = 1", ["A"]),
        ("from enum import Enum\nclass O:\n    class B(Enum):\n        pass\nclass E(B):\n    A = 1", ["A"]),
        ("def f() -> None:\n    from enum import Enum\nclass E(Enum):\n    A = 1", ["A"]),
        ("from enum import Enum\nclass B(Enum):\n    pass\ndef f() -> None:\n    import B\n    class C(B):\n        A = 1", ["A"]),
        ("from enum import Enum\nclass B(Enum):\n    pass\ndef f() -> None:\n    from m import B\n    class C(B):\n        A = 1", ["A"]),
        ("from enum import Enum\nclass B(Enum):\n    pass\ndef f() -> None:\n    class B:\n        pass\n    class C(B):\n        A = 1", ["A"]),
    ],
    ids=[
        "in-file-enum-base",
        "in-file-enum-base-in-class-body",
        "in-file-enum-base-in-function",
        "enum-module-in-class-body",
        "enum-module-in-function",
        "non-enum-base",
        "subscripted-base",
        "unimported-enum-name",
        "enum-module-non-base",
        "relative-enum-module",
        "enum-module-attribute-non-base",
        "other-module-attribute",
        "dotted-in-file-enum-name",
        "shadowed-by-class",
        "shadowed-by-import",
        "enum-module-shadowed-by-import",
        "tuple-target-in-enum",
        "starred-target-in-enum",
        "method-local-in-enum",
        "enum-in-function-stays-local",
        "enum-in-class-body-stays-local",
        "import-in-function-stays-local",
        "in-file-enum-shadowed-by-import",
        "in-file-enum-shadowed-by-from-import",
        "in-file-enum-shadowed-by-class",
    ],
)
def test_enum_recognition(source: str, expected: list[str]) -> None:
    """An enum base is resolved through imports from ``enum`` and in-file enum classes; everything else in an enum is still checked."""
    assert names(source) == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("class C:\n    limit: int = 3\n    def f(self) -> None:\n        limit = 4", ["limit"]),
        ("from enum import Enum\nclass E(Enum):\n    label = 1\n    def f(self) -> None:\n        label = 2", ["label"]),
        ("class O:\n    x: int = 1\n    class I:\n        def f(self) -> None:\n            x = 2", ["x"]),
        ("class O:\n    x: int = 1\n    class I:\n        x = 2", ["x"]),
        ("x: int\nclass C:\n    def f(self) -> None:\n        x = 1", []),
        ("def g() -> None:\n    x: int\n    class C:\n        def f(self) -> None:\n            x = 1", []),
    ],
    ids=["class-attribute", "enum-member", "outer-class-body", "nested-class-body", "module-declaration", "enclosing-function-declaration"],
)
def test_class_body_names_do_not_declare_inner_scopes(source: str, expected: list[str]) -> None:
    """A class body is not an enclosing scope for its methods or nested classes, so its names declare nothing there."""
    assert names(source) == expected


STDLIB_ENUM_BASES: frozenset[str] = frozenset({"enum.Enum", "enum.IntEnum", "enum.StrEnum", "enum.Flag", "enum.IntFlag", "enum.ReprEnum"})
CONFIGURED: frozenset[str] = frozenset({"myproject.base.BaseStatus", "django.db.models.TextChoices"})
NOT_CONFIGURED_HINT: str = "list it in enum-bases under [tool.check-declarations] in pyproject.toml"


@pytest.mark.parametrize(
    "source",
    [
        "from myproject.base import BaseStatus\nclass S(BaseStatus):\n    DONE = 1",
        "from myproject.base import BaseStatus as B\nclass S(B):\n    DONE = 1",
        "from myproject import base\nclass S(base.BaseStatus):\n    DONE = 1",
        "import myproject.base\nclass S(myproject.base.BaseStatus):\n    DONE = 1",
        "import myproject.base as b\nclass S(b.BaseStatus):\n    DONE = 1",
        "from django.db import models\nclass C(models.TextChoices):\n    RED = 'r'",
    ],
    ids=["from-import", "from-import-alias", "module-from-package", "dotted-import", "dotted-import-alias", "third-party-module-attribute"],
)
def test_configured_enum_bases_are_recognized(source: str) -> None:
    """A base named in ``enum-bases`` is an enum, however it is imported."""
    assert check_source(Path("t.py"), source, enum_bases=CONFIGURED) == []


@pytest.mark.parametrize(
    ("package", "source", "expected"),
    [
        ("myproject", "from .base import BaseStatus\nclass S(BaseStatus):\n    DONE = 1", []),
        ("myproject.sub", "from ..base import BaseStatus\nclass S(BaseStatus):\n    DONE = 1", []),
        ("myproject", "from . import base\nclass S(base.BaseStatus):\n    DONE = 1", []),
        ("myproject", "def f() -> None:\n    from .base import BaseStatus\n    class S(BaseStatus):\n        DONE = 1", []),
        ("myproject", "from ..base import BaseStatus\nclass S(BaseStatus):\n    DONE = 1", ["DONE"]),
        ("", "from .base import BaseStatus\nclass S(BaseStatus):\n    DONE = 1", ["DONE"]),
        ("myproject", "from myproject.base import BaseStatus\nfrom ..base import BaseStatus\nclass S(BaseStatus):\n    DONE = 1", ["DONE"]),
    ],
    ids=["same-package", "parent-package", "module-from-own-package", "inside-a-function", "beyond-top-level", "not-in-a-package", "unresolved-replaces-resolved"],
)
def test_relative_imports_resolve_against_the_package(package: str, source: str, expected: list[str]) -> None:
    """A relative import names the same base as its absolute form; one that leaves the package names nothing, so no hint."""
    violations: list[Violation] = check_source(Path("t.py"), source, enum_bases=CONFIGURED, package=package)
    assert [(violation.name, violation.hint) for violation in violations] == [(name, "") for name in expected]


def test_unconfigured_imported_base_hints_at_the_setting() -> None:
    violations: list[Violation] = check_source(Path("t.py"), "from myproject.base import BaseStatus\nclass S(BaseStatus):\n    DONE = 1")
    assert [violation.render() for violation in violations] == [
        f"t.py:3:4: DONE bound before annotation (if myproject.base.BaseStatus is an enum, {NOT_CONFIGURED_HINT})",
    ]


def test_hint_names_every_imported_base() -> None:
    violations: list[Violation] = check_source(Path("t.py"), "import a\nimport b\nclass S(a.X, b.Y):\n    DONE = 1")
    assert [violation.hint for violation in violations] == [f"if a.X or b.Y is an enum, {NOT_CONFIGURED_HINT}"]


@pytest.mark.parametrize(
    "source",
    [
        "x = 1",
        "class P:\n    pass\nclass S(P):\n    DONE = 1",
        "from m import B\nclass S(B):\n    def f(self) -> None:\n        x = 1",
        "from m import B\nclass B:\n    pass\nclass S(B):\n    DONE = 1",
        "class S(ns.Base):\n    DONE = 1",
        "from .base import B\nclass S(B):\n    DONE = 1",
        "from enum import Enum\nclass E(Enum):\n    A, *B = 1, 2",
    ],
    ids=["module-binding", "in-file-base", "method-local", "shadowed-import", "unimported-dotted-base", "relative-import-outside-a-package", "violation-in-an-enum"],
)
def test_no_hint_without_an_imported_base(source: str) -> None:
    violations: list[Violation] = check_source(Path("t.py"), source)
    assert violations
    assert [violation.hint for violation in violations] == [""] * len(violations)
    assert violations[0].render().endswith("bound before annotation")


def test_package_of_walks_up_through_init_files(tmp_path: Path) -> None:
    (tmp_path / "pkg" / "sub").mkdir(parents=True)
    (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "pkg" / "sub" / "__init__.py").write_text("", encoding="utf-8")
    assert package_of(tmp_path / "pkg" / "sub" / "m.py") == "pkg.sub"
    assert package_of(tmp_path / "m.py") == ""


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("[project]\nname = 'x'\n", STDLIB_ENUM_BASES),
        ("[tool.check-declarations]\n", STDLIB_ENUM_BASES),
        ("[tool.check-declarations]\nenum-bases = ['myproject.base.BaseStatus']\n", STDLIB_ENUM_BASES | {"myproject.base.BaseStatus"}),
    ],
    ids=["no-tool-section", "no-enum-bases", "configured"],
)
def test_load_enum_bases(tmp_path: Path, text: str, expected: frozenset[str]) -> None:
    pyproject: Path = tmp_path / "pyproject.toml"
    pyproject.write_text(text, encoding="utf-8")
    assert load_enum_bases(pyproject) == expected


def test_load_enum_bases_without_a_pyproject(tmp_path: Path) -> None:
    assert load_enum_bases(tmp_path / "pyproject.toml") == STDLIB_ENUM_BASES


@pytest.mark.parametrize("value", ["'myproject.base.BaseStatus'", "[1]"], ids=["not-a-list", "not-strings"])
def test_load_enum_bases_rejects_a_malformed_setting(tmp_path: Path, value: str) -> None:
    pyproject: Path = tmp_path / "pyproject.toml"
    pyproject.write_text(f"[tool.check-declarations]\nenum-bases = {value}\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"^\[tool\.check-declarations\] enum-bases must be a list of strings$"):
        load_enum_bases(pyproject)


def test_main_reads_enum_bases_and_resolves_the_package(tmp_path: Path) -> None:
    pyproject: Path = tmp_path / "pyproject.toml"
    pyproject.write_text("[tool.check-declarations]\nenum-bases = ['pkg.base.BaseStatus']\n", encoding="utf-8")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    module: Path = tmp_path / "pkg" / "status.py"
    module.write_text("from .base import BaseStatus\nclass S(BaseStatus):\n    DONE = 1\n", encoding="utf-8")
    assert main([str(module)], pyproject=pyproject) == 0
    assert main([str(module)], pyproject=tmp_path / "missing.toml") == 1


def test_main_reports_an_unreadable_pyproject(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    pyproject: Path = tmp_path / "pyproject.toml"
    pyproject.write_text("[tool.check-declarations]\nenum-bases = 1\n", encoding="utf-8")
    module: Path = tmp_path / "m.py"
    module.write_text("x: int = 1\n", encoding="utf-8")
    assert main([str(module)], pyproject=pyproject) == 1
    assert capsys.readouterr().err == f"{pyproject}: [tool.check-declarations] enum-bases must be a list of strings\n"
