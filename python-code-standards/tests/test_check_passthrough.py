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
