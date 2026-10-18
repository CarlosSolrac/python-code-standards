"""Tests for the design-spec eval grader.

Like ``evals/grade.py``, this grader's failure mode is a confident wrong answer, so
the tests pin both directions: a check passes only on what it can fully decide, and
anything it cannot decide is reported ``manual``, never ``pass``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from evals.design_spec_grade import Result, Rule, Run, Verdict, grade


def _run(spec: str | None = None, reply: str | None = None) -> Run:
    """Return run inputs for checks that read only the spec and the reply."""
    return Run(fixture=Path("fixture"), commit="abc1234", spec_path=Path("fixture/docs/design.md"), spec=spec, reply=reply)


def _passes(run: Run) -> Verdict:
    del run
    return Verdict(passed=True, evidence="looked and it holds")


def _fails(run: Run) -> Verdict:
    del run
    return Verdict(passed=False, evidence="looked and it does not")


def test_grade_reports_each_assertion_in_order() -> None:
    assertions: list[str] = ["The first line states it", "Judged by a person", "No code is changed"]
    rules: list[Rule] = [Rule("No code is changed", _fails), Rule("The first line states it", _passes)]
    assert grade(assertions, rules, _run()) == [
        Result("The first line states it", "pass", "looked and it holds"),
        Result("Judged by a person", "manual", "judgment: grade by hand"),
        Result("No code is changed", "fail", "looked and it does not"),
    ]


def test_grade_leaves_the_rest_of_a_partly_mechanical_assertion_to_a_person() -> None:
    assertions: list[str] = ["A table with these columns has a row per boundary"]
    assert grade(assertions, [Rule("A table with these columns has a row per boundary", _passes, complete=False)], _run()) == [
        Result("A table with these columns has a row per boundary", "manual", "looked and it holds; the rest needs a person"),
    ]


def test_grade_fails_a_partly_mechanical_assertion_whose_mechanical_part_fails() -> None:
    assertions: list[str] = ["A table with these columns has a row per boundary"]
    assert grade(assertions, [Rule("A table with these columns has a row per boundary", _fails, complete=False)], _run()) == [
        Result("A table with these columns has a row per boundary", "fail", "looked and it does not"),
    ]


@pytest.mark.parametrize(
    ("assertions", "count"),
    [(["The first line states it, reworded"], 0), (["The first line states it", "The first line states it"], 2)],
    ids=["reworded", "duplicated"],
)
def test_grade_refuses_a_rule_whose_assertion_is_not_there_exactly_once(assertions: list[str], count: int) -> None:
    with pytest.raises(ValueError, match=f"the assertion 'The first line states it' appears {count} times"):
        grade(assertions, [Rule("The first line states it", _passes)], _run())


def test_grade_refuses_two_rules_for_one_assertion() -> None:
    with pytest.raises(ValueError, match="two rules decide 'No code is changed'"):
        grade(["No code is changed"], [Rule("No code is changed", _fails), Rule("No code is changed", _passes)], _run())
