"""Tests for the pass-through checker.

The definition is fixed, so each clause of it gets a positive case and the near
misses that sit just outside it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from skill.tools.check_passthrough import Finding, find_passthroughs


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
