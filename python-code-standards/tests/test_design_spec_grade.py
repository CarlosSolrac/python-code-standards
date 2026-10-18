"""Tests for the design-spec eval grader.

Like ``evals/grade.py``, this grader's failure mode is a confident wrong answer, so
the tests pin both directions: a check passes only on what it can fully decide, and
anything it cannot decide is reported ``manual``, never ``pass``.
"""

from __future__ import annotations

import io
import json
import runpy
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import pytest

from evals.design_spec_grade import CLOSING, EMPTY_TREE, EVALS, GRADER_VERSION, RULES, Check, Result, Rule, Run, Verdict, bind, closing_line, first_line, grade, main


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


@dataclass
class Recorder:
    """A check that records the run it was given and passes."""

    runs: list[Run] = field(default_factory=list[Run])

    def __call__(self, run: Run) -> Verdict:
        """Record the run."""
        self.runs.append(run)
        return Verdict(passed=True, evidence="recorded")


def _evals(tmp_path: Path) -> Path:
    """Write an evals.json with eval 1, eval 3 and eval 5 (3b), two assertions each."""
    path: Path = tmp_path / "evals.json"
    entries: list[dict[str, object]] = [{"id": number, "name": f"eval-{number}", "assertions": ["The first line states it", "Judged by a person"]} for number in (1, 3, 5)]
    path.write_text(json.dumps({"skill_name": "design-spec", "evals": entries}), encoding="utf-8")
    return path


def _fixture(tmp_path: Path, spec: str | None = "# Design\n") -> Path:
    """Make a fixture folder, with a spec in docs/design.md unless ``spec`` is None."""
    fixture: Path = tmp_path / "fixture"
    (fixture / "docs").mkdir(parents=True)
    if spec is not None:
        (fixture / "docs" / "design.md").write_text(spec, encoding="utf-8")
    return fixture


def test_main_prints_each_result_and_writes_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    fixture: Path = _fixture(tmp_path)
    out: Path = tmp_path / "grade.json"
    rules: dict[int, tuple[Rule, ...]] = {3: (Rule("The first line states it", _fails),)}
    assert main(["3", str(fixture), "abc1234", "--evals", str(_evals(tmp_path)), "--json", str(out)], rules=rules) == 0
    spec: Path = fixture.resolve() / "docs" / "design.md"
    assert capsys.readouterr().out.splitlines() == [
        f"design-spec grader {GRADER_VERSION} — eval 3 (eval-3)",
        f"fixture {fixture.resolve()} at abc1234",
        f"spec {spec}",
        "reply none given; reply checks are manual",
        "",
        "fail    The first line states it",
        "        looked and it does not",
        "manual  Judged by a person",
        "        judgment: grade by hand",
        "",
        "0 pass, 1 fail, 1 manual",
        f"wrote {out}",
    ]
    written: str = out.read_text(encoding="utf-8")
    assert written == json.dumps(json.loads(written), indent=2)
    assert json.loads(written) == {
        "grader_version": GRADER_VERSION,
        "eval_id": 3,
        "eval_name": "eval-3",
        "fixture": str(fixture.resolve()),
        "build_commit": "abc1234",
        "spec": str(spec),
        "reply": None,
        "results": [
            {"assertion": "The first line states it", "status": "fail", "evidence": "looked and it does not"},
            {"assertion": "Judged by a person", "status": "manual", "evidence": "judgment: grade by hand"},
        ],
    }


def test_main_hands_the_checks_the_spec_and_reply_it_was_given(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    recorder: Recorder = Recorder()
    fixture: Path = _fixture(tmp_path, spec=None)
    spec: Path = tmp_path / "answer.md"
    spec.write_text("# Answer\n", encoding="utf-8")
    reply: Path = tmp_path / "reply.txt"
    reply.write_text("Document mode, Standard.\n", encoding="utf-8")
    main(["3b", str(fixture), "abc1234", "--spec", str(spec), "--reply", str(reply), "--evals", str(_evals(tmp_path))], rules={5: (Rule("The first line states it", recorder),)})
    assert recorder.runs == [Run(fixture=fixture.resolve(), commit="abc1234", spec_path=spec.resolve(), spec="# Answer\n", reply="Document mode, Standard.\n")]
    assert f"reply {reply.resolve()}" in capsys.readouterr().out.splitlines()


def test_main_reads_no_spec_when_the_fixture_has_none(tmp_path: Path) -> None:
    recorder: Recorder = Recorder()
    fixture: Path = _fixture(tmp_path, spec=None)
    main(["3", str(fixture), "abc1234", "--evals", str(_evals(tmp_path))], rules={3: (Rule("The first line states it", recorder),)})
    assert recorder.runs[0].spec is None
    assert recorder.runs[0].spec_path == fixture.resolve() / "docs" / "design.md"


def test_main_compares_eval_1_with_the_empty_tree(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    recorder: Recorder = Recorder()
    main(["1", str(_fixture(tmp_path)), "--evals", str(_evals(tmp_path))], rules={1: (Rule("The first line states it", recorder),)})
    assert recorder.runs[0].commit == EMPTY_TREE
    assert f"fixture {(tmp_path / 'fixture').resolve()} at {EMPTY_TREE} (no commits)" in capsys.readouterr().out.splitlines()


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["3", "fixture"], "eval 3 needs its build commit"),
        (["4", "fixture", "abc1234"], "no eval 4 in"),
        (["3c", "fixture", "abc1234"], "invalid eval_id value: '3c'"),
    ],
    ids=["no-commit", "not-in-evals", "bad-id"],
)
def test_main_rejects_bad_arguments(tmp_path: Path, capsys: pytest.CaptureFixture[str], argv: list[str], message: str) -> None:
    exit_info: pytest.ExceptionInfo[SystemExit]
    with pytest.raises(SystemExit) as exit_info:
        main([*argv, "--evals", str(_evals(tmp_path))], rules={})
    assert exit_info.value.code == 2
    assert message in capsys.readouterr().err


def test_rules_match_the_assertions_in_evals_json() -> None:
    document: dict[str, list[dict[str, object]]] = json.loads(EVALS.read_text(encoding="utf-8"))
    ids: set[object] = {entry["id"] for entry in document["evals"]}
    assert set(RULES) <= ids
    entry: dict[str, object]
    for entry in document["evals"]:
        bind(cast("list[str]", entry["assertions"]), RULES.get(cast("int", entry["id"]), ()))


def test_main_grades_against_the_repository_evals_by_default(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    main(["2", str(_fixture(tmp_path)), "abc1234"], rules={})
    assert "eval 2 (eval-2-small)" in capsys.readouterr().out


def test_runs_as_script(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """Executed as a script, the module hands control to ``main``."""
    script: Path = Path(__file__).parent.parent / "evals" / "design_spec_grade.py"
    monkeypatch.setattr(sys, "argv", [str(script), "--help"])
    monkeypatch.setenv("COLUMNS", "200")
    exit_info: pytest.ExceptionInfo[SystemExit]
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_path(str(script), run_name="__main__")
    assert exit_info.value.code == 0
    assert "Grade a design-spec eval run on what a tool can decide." in capsys.readouterr().out


@pytest.mark.parametrize(
    ("reply", "mode", "size", "passed"),
    [
        ("Document mode, Standard with a context view.\nThe rest.", "document", None, True),
        ("\n  **Mode:** design · **Size:** Standard\n", "design", "Standard", True),
        ("Small: one typed module, no spec.", None, "Small", True),
        ("Design mode, Large.", "design", "Standard", False),
        ("Document mode.", "document", None, False),
        ("Design Spec, document mode, Standard.", "design", "Standard", False),
        ("The spec.\nDocument mode, Standard.", "document", None, False),
        ("Design — Standard", "design", "Standard", True),
        ("Design Spec, document mode, Standard.", "document", None, True),
        ("Document — Standard, the design of tally", "document", None, False),
        ("Design mode or document mode, Standard", "design", None, False),
        ("Design/document mode, Standard", "document", None, False),
        ("Using the design-spec skill: document mode, Standard.", "document", None, True),
        ("Design mode — using standard libraries", "design", "Standard", False),
        ("Design mode, size: standard", "design", "Standard", True),
        ("Document mode, a standard-size spec", "document", None, True),
    ],
    ids=[
        "document-any-size",
        "design-standard",
        "small-only",
        "wrong-size",
        "no-size",
        "design-only-as-a-name",
        "not-the-first-line",
        "mode-word-omitted",
        "named-mode-wins",
        "both-modes-bare",
        "both-modes-named",
        "modes-joined-by-a-slash",
        "skill-name-is-not-a-mode",
        "lowercase-word-is-not-a-size",
        "lowercase-size-labelled",
        "lowercase-size-adjacent",
    ],
)
def test_first_line_states_the_mode_and_size(reply: str, mode: str | None, size: str | None, *, passed: bool) -> None:
    line: str = next(line.strip() for line in reply.splitlines() if line.strip())
    verdict: Verdict = first_line(mode, size)(_run(reply=reply))
    assert verdict.passed is passed
    assert verdict.evidence.startswith(f"first line: {line!r}" if passed else f"first line {line!r} does not state ")


def test_first_line_names_what_it_wanted() -> None:
    assert first_line("design", "Standard")(_run(reply="Large.")).evidence == "first line 'Large.' does not state design mode and the Standard size class"
    assert first_line("document", None)(_run(reply="Mode.")).evidence == "first line 'Mode.' does not state document mode and a size class"
    assert first_line(None, "Small")(_run(reply="Big.")).evidence == "first line 'Big.' does not state the Small size class"


@pytest.mark.parametrize(
    ("reply", "passed"),
    [
        (f"The spec.\n\n{CLOSING}\n\n", True),
        (f"The spec.\n**{CLOSING}**", True),
        (f"Open questions above. {CLOSING}", True),
        (f"{CLOSING}\nThanks.", False),
    ],
    ids=["plain", "bold", "end-of-a-sentence", "not-last"],
)
def test_closing_line_ends_the_reply(reply: str, *, passed: bool) -> None:
    line: str = [line.strip() for line in reply.splitlines() if line.strip()][-1]
    verdict: Verdict = closing_line(_run(reply=reply))
    assert verdict == Verdict(passed=passed, evidence=f"last line: {line!r}" if passed else f"last line {line!r} does not end with {CLOSING!r}")


@pytest.mark.parametrize("check", [first_line("document", None), closing_line], ids=["first-line", "closing-line"])
def test_reply_checks_without_a_reply_are_manual(check: Check) -> None:
    assert grade(["A"], [Rule("A", check)], _run(reply=None)) == [Result("A", "manual", "no --reply given; grade by hand")]


@pytest.mark.parametrize("check", [first_line("document", None), closing_line], ids=["first-line", "closing-line"])
def test_reply_checks_fail_an_empty_reply(check: Check) -> None:
    assert check(_run(reply="\n  \n")) == Verdict(passed=False, evidence="the reply is empty")


def test_main_prints_utf8_whatever_the_console_encoding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A Windows pipe defaults to cp1252, which cannot encode an arrow quoted from a reply."""
    buffer: io.BytesIO = io.BytesIO()
    stdout: io.TextIOWrapper = io.TextIOWrapper(buffer, encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", stdout)
    reply: Path = tmp_path / "reply.txt"
    reply.write_text("Document mode → Standard\n", encoding="utf-8")
    main(["3", str(_fixture(tmp_path)), "abc1234", "--reply", str(reply), "--evals", str(_evals(tmp_path))], rules={3: (Rule("The first line states it", first_line("document", None)),)})
    stdout.flush()
    assert "first line: 'Document mode → Standard'" in buffer.getvalue().decode("utf-8")


def test_main_prints_to_a_stream_that_cannot_be_reconfigured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stdout: io.StringIO = io.StringIO()
    monkeypatch.setattr(sys, "stdout", stdout)
    main(["3", str(_fixture(tmp_path)), "abc1234", "--evals", str(_evals(tmp_path))], rules={})
    assert "0 pass, 0 fail, 2 manual" in stdout.getvalue()
