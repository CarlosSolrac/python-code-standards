"""Tests for the pass-through checker.

The definition is fixed, so each clause of it gets a positive case and the near
misses that sit just outside it.
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

import pytest

from skill.tools.check_passthrough import Finding, find_passthroughs, iter_python_files, main


def found(source: str) -> list[str]:
    """Return the names reported as pass-throughs, in source order."""
    findings: list[Finding] = find_passthroughs(Path("t.py"), source)
    return [finding.name for finding in findings]


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("def f(x):\n    return g(x)", ["f"]),
        ("def f(x):\n    g(x)", ["f"]),
        ("async def f(x):\n    return await g(x)", ["f"]),
        ("async def f(x):\n    await g(x)", ["f"]),
        ("async def f(x):\n    return g(x)", ["f"]),
        ("def f(x):\n    '''Doc.'''\n    return g(x)", ["f"]),
        ("def f():\n    return g()", ["f"]),
        ("def f(x):\n    return g(x)\n\ndef h(y):\n    return k(y)", ["f", "h"]),
        ("class C:\n    def f(self, x):\n        return g(x)", ["f"]),
        ("def outer():\n    x = 1\n    def inner(y):\n        return g(y)\n    return inner", ["inner"]),
    ],
    ids=["return-call", "bare-call", "return-await", "bare-await", "async-return-unawaited", "docstring", "no-parameters", "two-findings", "method", "nested"],
)
def test_one_forwarding_statement_is_a_passthrough(source: str, expected: list[str]) -> None:
    """A single ``return <call>`` or ``<call>``, awaited or not, after an optional docstring."""
    assert found(source) == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("def f(x):\n    return x", []),
        ("def f(x):\n    return", []),
        ("def f(x):\n    return g(x) + 1", []),
        ("def f(x):\n    return not g(x)", []),
        ("def f(x):\n    y = g(x)", []),
        ("def f(x):\n    '''Doc.'''", []),
        ("def f(x):\n    pass", []),
        ("def f(x):\n    '''Doc.'''\n    g(x)\n    return h(x)", []),
        ("def f(x):\n    g(x)\n    return h(x)", []),
        ("def f(x):\n    'text'\n    'more'\n    return g(x)", []),
        ("def f(x):\n    return g(x) if x else None", []),
        ("def f(x):\n    return [g(x)]", []),
        ("def f(x):\n    return (yield g(x))", []),
        ("async def f(x):\n    return await x", []),
    ],
    ids=[
        "returns-parameter",
        "bare-return",
        "arithmetic-on-call",
        "unary-on-call",
        "assignment",
        "docstring-only",
        "pass-only",
        "two-statements-after-docstring",
        "two-statements",
        "second-string-is-a-statement",
        "conditional",
        "list-of-call",
        "yield",
        "await-non-call",
    ],
)
def test_other_bodies_are_not_passthroughs(source: str, expected: list[str]) -> None:
    """Anything but one forwarding call, once the docstring is set aside, is not reported."""
    assert found(source) == expected


def test_finding_reports_the_line_of_the_def() -> None:
    """The line is the ``def`` line, not the first decorator's."""
    findings: list[Finding] = find_passthroughs(Path("t.py"), "x: int = 1\n\n@property\ndef f(self):\n    return g()\n")
    assert findings == [Finding(Path("t.py"), 4, "f")]


@pytest.mark.parametrize(
    "source",
    [
        "def f(x, y):\n    return g(x, y)",
        "def f(x, y):\n    return g(y, x)",
        "def f(x, y):\n    return g(a=x, b=y)",
        "def f(x, y):\n    return g(b=y, a=x)",
        "def f(x, y):\n    return g(x, b=y)",
        "def f(*args):\n    return g(*args)",
        "def f(**kwargs):\n    return g(**kwargs)",
        "def f(x, *args, **kwargs):\n    return g(x, *args, **kwargs)",
        "def f(x, *args, **kwargs):\n    return g(*args, x, **kwargs)",
        "def f(*, a):\n    return g(a=a)",
        "def f(a, /, b):\n    return g(a, b)",
        "def f(a, /):\n    return g(a)",
        "class C:\n    def total(self):\n        return self._inner.total()",
        "class C:\n    def add(self, x):\n        return self._inner.add(x)",
        "class C:\n    @classmethod\n    def make(cls, x):\n        return build(x)",
        "class C:\n    def f(self, x):\n        return get().go(x)",
        "def f(x=1):\n    return g(x)",
    ],
    ids=[
        "positional",
        "reordered",
        "by-keyword",
        "reordered-keywords",
        "mixed",
        "star-args",
        "star-star-kwargs",
        "all-kinds",
        "star-args-before-positional",
        "keyword-only",
        "positional-only",
        "positional-only-alone",
        "method-without-other-parameters",
        "method-with-parameter",
        "classmethod",
        "any-callee",
        "default-value",
    ],
)
def test_every_parameter_passed_once_unchanged_is_a_passthrough(source: str) -> None:
    """Arguments that are exactly the parameters, once each, in any order or form, excluding ``self`` and ``cls``."""
    assert len(found(source)) == 1


@pytest.mark.parametrize(
    "source",
    [
        "def f(x):\n    return g(x + 1)",
        "def f(x):\n    return g(x, 1)",
        "def f(x):\n    return g(x, extra=1)",
        "def f(x, y):\n    return g(x)",
        "def f(x):\n    return g()",
        "def f(x):\n    return g(x, x)",
        "def f(x):\n    return g(x, b=x)",
        "def f(x):\n    return g(h(x))",
        "def f(x):\n    return g(x.attr)",
        "def f(x):\n    return g(-x)",
        "def f(x):\n    return g(x, z)",
        "def f(*args):\n    return g(args)",
        "def f(*args):\n    return g()",
        "def f(*args):\n    return g(*args, *args)",
        "def f(*args):\n    return g(*args[1:])",
        "def f(**kwargs):\n    return g(kwargs)",
        "def f(**kwargs):\n    return g(**kwargs, **kwargs)",
        "def f(**kwargs):\n    return g(**dict(kwargs))",
        "def f(x):\n    return g(*x)",
        "def f(x):\n    return g(**x)",
        "def f(x):\n    return g(*other)",
        "def f(x, *args):\n    return g(x, args=args)",
        "def f(*args, **kwargs):\n    return g(*kwargs, **args)",
        "def f(x):\n    return g(*[x])",
        "def f(x):\n    return g(**{'a': x})",
        "class C:\n    def f(self, x):\n        return g(self, x)",
        "class C:\n    @classmethod\n    def f(cls, x):\n        return g(cls, x)",
        "class C:\n    def f(self):\n        return g(self)",
    ],
    ids=[
        "added-to-argument",
        "added-constant-positional",
        "added-constant-keyword",
        "dropped-argument",
        "dropped-only-argument",
        "passed-twice",
        "passed-twice-by-keyword",
        "transformed-by-call",
        "attribute-of-argument",
        "unary-on-argument",
        "unknown-name",
        "varargs-as-tuple",
        "varargs-dropped",
        "varargs-twice",
        "varargs-sliced",
        "kwargs-as-dict",
        "kwargs-twice",
        "kwargs-rebuilt",
        "parameter-unpacked-as-star",
        "parameter-unpacked-as-star-star",
        "star-of-unknown-name",
        "keyword-named-like-varargs",
        "star-args-swapped",
        "parameter-wrapped-in-list-star",
        "parameter-wrapped-in-dict-star-star",
        "receiver-passed-on",
        "class-receiver-passed-on",
        "only-receiver-passed-on",
    ],
)
def test_arguments_that_differ_from_the_parameters_are_not_a_passthrough(source: str) -> None:
    """An added, transformed, dropped or repeated argument makes the call real work."""
    assert found(source) == []


@pytest.mark.parametrize(
    "decorator",
    ["overload", "typing.overload", "typing_extensions.overload", "abstractmethod", "abc.abstractmethod"],
)
def test_overloads_and_abstract_methods_are_skipped(decorator: str) -> None:
    """A declaration that must exist for the type checker or a subclass is not a function to delete."""
    assert found(f"class C:\n    @{decorator}\n    def f(self, x):\n        return g(x)") == []


def test_a_skipped_decorator_among_others_still_skips() -> None:
    """The skip applies wherever the decorator sits in the stack, and to ``async def`` too."""
    assert found("class C:\n    @staticmethod\n    @abstractmethod\n    async def f(x):\n        return await g(x)\n") == []
    assert found("class C:\n    @abstractmethod\n    @staticmethod\n    def f(x):\n        return g(x)\n") == []


@pytest.mark.parametrize(
    "decorator",
    ["property", "staticmethod", "functools.cache", "wraps(g)", "overloaded", "my_overload", "abstractmethod_", "overload(1)", "overload.other", "abstractmethod()"],
)
def test_other_decorators_do_not_skip(decorator: str) -> None:
    """Only ``overload`` and ``abstractmethod``, bare or through a module, are skipped."""
    assert found(f"class C:\n    @{decorator}\n    def f(x):\n        return g(x)") == ["f"]


def test_finding_renders_as_path_line_name() -> None:
    """One ``path:line name`` per finding."""
    assert Finding(Path("pkg/m.py"), 7, "total").render() == "pkg/m.py:7 total"


def test_iter_python_files_takes_files_as_given_and_walks_directories(tmp_path: Path) -> None:
    """A directory yields its ``.py`` files, sorted and recursive; other suffixes and directories named ``*.py`` are left out, explicit files included."""
    (tmp_path / "pkg").mkdir()
    (tmp_path / "dir.py").mkdir()
    (tmp_path / "b.py").write_text("", encoding="utf-8")
    (tmp_path / "a.py").write_text("", encoding="utf-8")
    (tmp_path / "pkg" / "c.py").write_text("", encoding="utf-8")
    (tmp_path / "n.ipynb").write_text("", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("", encoding="utf-8")
    explicit: Path = tmp_path / "pkg" / "c.py"
    assert list(iter_python_files([tmp_path])) == [tmp_path / "a.py", tmp_path / "b.py", explicit]
    assert list(iter_python_files([explicit, tmp_path / "notes.txt", tmp_path / "a.py"])) == [explicit, tmp_path / "a.py"]


def test_main_prints_each_finding_and_exits_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Findings go to stdout as ``path:line name``, across files, in argument order."""
    first: Path = tmp_path / "first.py"
    second: Path = tmp_path / "second.py"
    first.write_text("def a(x):\n    return g(x)\n\n\ndef b(x):\n    return g(x + 1)\n", encoding="utf-8")
    second.write_text("class C:\n    def total(self):\n        return self._inner.total()\n", encoding="utf-8")
    assert main([str(second), str(first)]) == 1
    out: str
    err: str
    out, err = capsys.readouterr()
    assert out == f"{second}:2 total\n{first}:1 a\n"
    assert err == ""


def test_main_exits_0_and_prints_nothing_when_clean(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """No findings, no output, status 0."""
    module: Path = tmp_path / "m.py"
    module.write_text("def f(x):\n    return g(x + 1)\n", encoding="utf-8")
    assert main([str(module)]) == 0
    assert capsys.readouterr() == ("", "")


def test_main_reports_a_file_it_cannot_parse(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A syntax error is named on stderr and fails the run, rather than passing it silently."""
    module: Path = tmp_path / "bad.py"
    module.write_text("def f(:\n", encoding="utf-8")
    assert main([str(module)]) == 1
    out: str
    err: str
    out, err = capsys.readouterr()
    assert out == ""
    assert err.startswith(f"{module}:1:")
    assert "could not parse" in err


@pytest.mark.parametrize(
    ("content", "line"),
    [
        (b"\xef\xbb\xbfdef f(x):\n    return g(x)\n", 1),
        (b"# coding: latin-1\n# caf\xe9\ndef f(x):\n    return g(x)\n", 3),
    ],
    ids=["utf-8-bom", "encoding-cookie"],
)
def test_main_reads_source_the_way_python_does(tmp_path: Path, capsys: pytest.CaptureFixture[str], content: bytes, line: int) -> None:
    """A byte-order mark or an encoding declaration is honoured, so a valid module is checked rather than rejected."""
    module: Path = tmp_path / "m.py"
    module.write_bytes(content)
    assert main([str(module)]) == 1
    assert capsys.readouterr() == (f"{module}:{line} f\n", "")


def test_main_rejects_a_path_that_does_not_exist(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A mistyped path fails the run instead of passing it with nothing checked."""
    module: Path = tmp_path / "m.py"
    module.write_text("def f(x):\n    return g(x + 1)\n", encoding="utf-8")
    missing: Path = tmp_path / "nope"
    assert main([str(module), str(missing)]) == 1
    assert capsys.readouterr() == ("", f"{missing}: no such file or directory\n")


def test_help_shows_the_module_docstring(capsys: pytest.CaptureFixture[str]) -> None:
    """``--help`` describes what a pass-through is."""
    with pytest.raises(SystemExit):
        main(["--help"])
    assert "Report functions that only forward their arguments." in capsys.readouterr().out


def test_runs_as_script(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Executed as a script, the module exits with ``main``'s status."""
    module: Path = tmp_path / "m.py"
    module.write_text("def f(x):\n    return g(x)\n", encoding="utf-8")
    script: Path = Path(__file__).parent.parent / "skill" / "tools" / "check_passthrough.py"
    monkeypatch.setattr(sys, "argv", [str(script), str(module)])
    exit_info: pytest.ExceptionInfo[SystemExit]
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_path(str(script), run_name="__main__")
    assert exit_info.value.code == 1
