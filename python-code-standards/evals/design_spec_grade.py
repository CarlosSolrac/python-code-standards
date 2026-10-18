"""Grade a design-spec eval run on what a tool can decide.

A design-spec eval is a real session graded by hand against the assertions in
``design-spec/evals/evals.json``. Some of those assertions are mechanical: every
diagram parses, every cited ``path:line`` exists at the build commit, no code
changed. This grader decides those and reports every other assertion ``manual``,
so a ``pass`` here always comes from a tool, never from a guess.

An assertion that mixes a mechanical part with judgment fails when the mechanical
part fails, and is otherwise ``manual`` with that part's evidence.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

type Status = Literal["pass", "fail", "manual"]


@dataclass(frozen=True)
class Run:
    """What a check may look at: the fixture, its build commit, the spec, and the reply."""

    fixture: Path
    commit: str | None
    spec_path: Path
    spec: str | None
    reply: str | None


@dataclass(frozen=True)
class Verdict:
    """A check's answer and the evidence for it."""

    passed: bool
    evidence: str


type Check = Callable[[Run], Verdict]


@dataclass(frozen=True)
class Rule:
    """A check bound to the assertion it decides.

    ``assertion`` is the assertion's full text in ``evals.json``, so a reworded or
    removed assertion makes the rule stale instead of silently grading something
    else. ``complete`` is False when the check decides only part of the assertion.
    """

    assertion: str
    check: Check
    complete: bool = True


@dataclass(frozen=True)
class Result:
    """The grade of one assertion."""

    assertion: str
    status: Status
    evidence: str


def grade(assertions: Sequence[str], rules: Sequence[Rule], run: Run) -> list[Result]:
    """Grade each assertion with the rule that decides it, or report it ``manual``.

    Raises:
        ValueError: A rule's assertion is not among these assertions exactly once,
            or two rules decide the same assertion, so the rules no longer describe
            these assertions.
    """
    by_assertion: dict[str, Rule] = {}
    rule: Rule
    for rule in rules:
        count: int = list(assertions).count(rule.assertion)
        if count != 1:
            message: str = f"the assertion {rule.assertion!r} appears {count} times; update the grader's rules"
            raise ValueError(message)
        if rule.assertion in by_assertion:
            message = f"two rules decide {rule.assertion!r}; update the grader's rules"
            raise ValueError(message)
        by_assertion[rule.assertion] = rule
    return [_decide(assertion, by_assertion.get(assertion), run) for assertion in assertions]


def _decide(assertion: str, rule: Rule | None, run: Run) -> Result:
    """Grade one assertion; a partial check that passes leaves the assertion to a person."""
    if rule is None:
        return Result(assertion, "manual", "judgment: grade by hand")
    verdict: Verdict = rule.check(run)
    if not verdict.passed:
        return Result(assertion, "fail", verdict.evidence)
    if not rule.complete:
        return Result(assertion, "manual", f"{verdict.evidence}; the rest needs a person")
    return Result(assertion, "pass", verdict.evidence)
