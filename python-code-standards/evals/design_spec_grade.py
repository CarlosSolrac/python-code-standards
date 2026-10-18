"""Grade a design-spec eval run on what a tool can decide.

A design-spec eval is a real session graded by hand against the assertions in
``design-spec/evals/evals.json``. Some of those assertions are mechanical: every
diagram parses, every cited ``path:line`` exists at the build commit, no code
changed. This grader decides those and reports every other assertion ``manual``,
so a ``pass`` here always comes from a tool, never from a guess.

An assertion that mixes a mechanical part with judgment fails when the mechanical
part fails, and is otherwise ``manual`` with that part's evidence. Assertions about
the session's reply (its first and last lines) need the reply saved as text and
passed with ``--reply``; without it they are ``manual``.

Usage:
    uv run python -m evals.design_spec_grade 3 /e/ds/eval3/parquettoxl 8ffaa6f --reply reply.md --json grade.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, TypedDict, cast

GRADER_VERSION: str = "1.0.0"
"""Bump on any change to what is graded, so grades from different versions are not compared."""

EVALS: Path = Path(__file__).resolve().parents[2] / "design-spec" / "evals" / "evals.json"
"""The design-spec evals whose assertions are graded."""

EMPTY_TREE: str = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
"""Git's empty tree: eval 1's fixture has no commit, so its changes are compared with nothing."""

CLOSING: str = "Approve or correct before I implement."
"""The line a design-mode reply ends with (design-spec SKILL.md section 3)."""

_MODES: tuple[str, ...] = ("design", "document")
_SKILL_NAME: re.Pattern[str] = re.compile(r"\bdesign[- ]spec\b", re.IGNORECASE)

type Status = Literal["pass", "fail", "manual"]


@dataclass(frozen=True)
class Run:
    """What a check may look at: the fixture, its build commit, the spec, and the reply."""

    fixture: Path
    commit: str
    spec_path: Path
    spec: str | None
    reply: str | None


@dataclass(frozen=True)
class Verdict:
    """A check's answer and the evidence for it; ``passed`` is None when its input is missing."""

    passed: bool | None
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


@dataclass(frozen=True)
class Report:
    """Every assertion of one eval, graded, with the inputs that produced the grades."""

    grader_version: str
    eval_id: int
    eval_name: str
    fixture: str
    build_commit: str
    spec: str
    reply: str | None
    results: list[Result]


class _Eval(TypedDict):
    """The part of an ``evals.json`` entry the grader reads."""

    id: int
    name: str
    assertions: list[str]


def main(argv: list[str] | None = None, rules: Mapping[int, Sequence[Rule]] | None = None) -> int:
    """Grade one eval run and print one entry per assertion.

    Args:
        argv: Command-line arguments, defaulting to ``sys.argv[1:]``.
        rules: The rules for each eval id, defaulting to ``RULES``.

    Returns:
        0 always; this reports, it does not gate.
    """
    parser: argparse.ArgumentParser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("eval_id", type=eval_id, help="the eval's id in evals.json; 3b is accepted for 5")
    parser.add_argument("fixture", type=Path, help="the fixture folder the session worked in")
    parser.add_argument("commit", nargs="?", default=None, help="the build commit build-fixture.sh printed; eval 1 has none")
    parser.add_argument("--spec", type=Path, default=None, help="the spec to grade (default: <fixture>/docs/design.md)")
    parser.add_argument("--reply", type=Path, default=None, help="the session's reply saved as text; without it the reply checks are manual")
    parser.add_argument("--evals", type=Path, default=EVALS, help="the evals.json to read the assertions from")
    parser.add_argument("--json", type=Path, default=None, help="also write the report as JSON to this file")
    args: argparse.Namespace = parser.parse_args(argv)

    number: int = args.eval_id
    entries: list[_Eval] = cast("list[_Eval]", json.loads(args.evals.read_text(encoding="utf-8"))["evals"])
    entry: _Eval | None = next((candidate for candidate in entries if candidate["id"] == number), None)
    if entry is None:
        parser.error(f"no eval {number} in {args.evals}")
    commit: str | None = args.commit
    if commit is None:
        if number != 1:
            parser.error(f"eval {number} needs its build commit, which build-fixture.sh printed")
        commit = EMPTY_TREE

    fixture: Path = args.fixture.resolve()
    spec_path: Path = (args.spec or fixture / "docs" / "design.md").resolve()
    reply_path: Path | None = args.reply.resolve() if args.reply is not None else None
    run: Run = Run(
        fixture=fixture,
        commit=commit,
        spec_path=spec_path,
        spec=spec_path.read_text(encoding="utf-8") if spec_path.is_file() else None,
        reply=reply_path.read_text(encoding="utf-8") if reply_path is not None else None,
    )
    report: Report = Report(
        grader_version=GRADER_VERSION,
        eval_id=number,
        eval_name=entry["name"],
        fixture=str(fixture),
        build_commit=commit,
        spec=str(spec_path),
        reply=str(reply_path) if reply_path is not None else None,
        results=grade(entry["assertions"], (RULES if rules is None else rules).get(number, ()), run),
    )
    _print(report)
    if args.json is not None:
        args.json.write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")
        print(f"wrote {args.json}")
    return 0


def eval_id(text: str) -> int:
    """Parse an eval id; ``3b`` is eval 5's label in the plans and in build-fixture.sh."""
    return 5 if text == "3b" else int(text)


def _print(report: Report) -> None:
    """Print the report: its inputs, one entry per assertion, and the totals.

    Output is UTF-8: evidence quotes the spec and the reply, and a Windows pipe's
    default encoding (cp1252) cannot encode characters such as arrows.
    """
    reconfigure: object = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8")
    no_commits: str = " (no commits)" if report.build_commit == EMPTY_TREE else ""
    print(f"design-spec grader {report.grader_version} — eval {report.eval_id} ({report.eval_name})")
    print(f"fixture {report.fixture} at {report.build_commit}{no_commits}")
    print(f"spec {report.spec}")
    print(f"reply {report.reply}" if report.reply is not None else "reply none given; reply checks are manual")
    print()
    result: Result
    for result in report.results:
        print(f"{result.status:<8}{result.assertion}")
        print(f"{'':<8}{result.evidence}")
    print()
    print(", ".join(f"{sum(result.status == status for result in report.results)} {status}" for status in ("pass", "fail", "manual")))


def grade(assertions: Sequence[str], rules: Sequence[Rule], run: Run) -> list[Result]:
    """Grade each assertion with the rule that decides it, or report it ``manual``."""
    by_assertion: dict[str, Rule] = bind(assertions, rules)
    return [_decide(assertion, by_assertion.get(assertion), run) for assertion in assertions]


def bind(assertions: Sequence[str], rules: Sequence[Rule]) -> dict[str, Rule]:
    """Map each assertion a rule decides to that rule.

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
    return by_assertion


def _decide(assertion: str, rule: Rule | None, run: Run) -> Result:
    """Grade one assertion; a partial check that passes leaves the assertion to a person."""
    if rule is None:
        return Result(assertion, "manual", "judgment: grade by hand")
    verdict: Verdict = rule.check(run)
    if verdict.passed is None:
        return Result(assertion, "manual", f"{verdict.evidence}; grade by hand")
    if not verdict.passed:
        return Result(assertion, "fail", verdict.evidence)
    if not rule.complete:
        return Result(assertion, "manual", f"{verdict.evidence}; the rest needs a person")
    return Result(assertion, "pass", verdict.evidence)


def first_line(mode: str | None, size: str | None) -> Check:
    """Return a check that the reply's first line states ``mode`` and ``size``.

    Args:
        mode: ``design`` or ``document``, or None when the assertion names no mode.
        size: ``Small``, ``Standard`` or ``Large``, or None for any size class.
    """
    parts: list[str] = [f"{mode} mode"] if mode else []
    parts.append(f"the {size} size class" if size else "a size class")
    wanted: str = " and ".join(parts)
    # A size class is written as SKILL.md names it ("Standard"), or in any case beside
    # the word "size" ("size: standard"), so "standard libraries" is not a size class.
    word: str = size or "Small|Standard|Large"
    size_pattern: re.Pattern[str] = re.compile(rf"\b(?:{word})\b|(?i:\bsize\W+(?:{word})\b|\b(?:{word})\W+size\b)")

    def check(run: Run) -> Verdict:
        line: str | Verdict = _reply_line(run, 0)
        if isinstance(line, Verdict):
            return line
        if (mode is None or _stated_mode(line) == mode) and size_pattern.search(line):
            return Verdict(passed=True, evidence=f"first line: {line!r}")
        return Verdict(passed=False, evidence=f"first line {line!r} does not state {wanted}")

    return check


def _stated_mode(line: str) -> str | None:
    """Return the one mode a line names, or None when it names neither or both.

    "Design — Standard" states design; "Design/document mode" states neither. The
    skill's own name ("design-spec") is not a mode.
    """
    words: str = _SKILL_NAME.sub("", line)
    stated: list[str] = [mode for mode in _MODES if re.search(rf"\b{mode}\b", words, re.IGNORECASE)]
    return stated[0] if len(stated) == 1 else None


def closing_line(run: Run) -> Verdict:
    """Check that the reply's last line ends with the approval request."""
    line: str | Verdict = _reply_line(run, -1)
    if isinstance(line, Verdict):
        return line
    if line.strip("*_ ").endswith(CLOSING):
        return Verdict(passed=True, evidence=f"last line: {line!r}")
    return Verdict(passed=False, evidence=f"last line {line!r} does not end with {CLOSING!r}")


def _reply_line(run: Run, index: int) -> str | Verdict:
    """Return the reply's non-blank line at ``index``, or the verdict when there is none to read."""
    if run.reply is None:
        return Verdict(passed=None, evidence="no --reply given")
    lines: list[str] = [line.strip() for line in run.reply.splitlines() if line.strip()]
    if not lines:
        return Verdict(passed=False, evidence="the reply is empty")
    return lines[index]


RULES: Mapping[int, Sequence[Rule]] = {
    1: (
        Rule("The first line states design mode and the Standard size class", first_line("design", "Standard")),
        Rule('The reply ends with "Approve or correct before I implement."', closing_line),
    ),
    2: (Rule("The first line states the Small size class", first_line(None, "Small")),),
    3: (Rule("The first line states document mode and a size class", first_line("document", None)),),
    4: (Rule("The first line states document mode and a size class", first_line("document", None)),),
    6: (
        Rule(
            "The first line states design mode and the Standard size class, and the spec treats tally as an existing codebase being restructured, not a new system",
            first_line("design", "Standard"),
            complete=False,
        ),
        Rule('The reply ends with "Approve or correct before I implement."', closing_line),
    ),
}
"""The rules for each eval id in ``evals.json``; an assertion without a rule is graded by hand."""


if __name__ == "__main__":
    raise SystemExit(main())
