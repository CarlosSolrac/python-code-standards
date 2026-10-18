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
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import cast

import pytest

from evals.design_spec_grade import (
    CITATION,
    CLOSING,
    DESIGN_COLUMNS,
    DOCUMENT_COLUMNS,
    EMPTY_TREE,
    EVALS,
    GRADER_VERSION,
    RULES,
    VALIDATOR,
    Check,
    Package,
    Result,
    Rule,
    Run,
    Status,
    Verdict,
    Workspace,
    bind,
    change_classdefs,
    citations_exist,
    closing_line,
    contract_header,
    contract_sources,
    dependency_matrix,
    diagrams_parse,
    documentation_only,
    find_evals,
    first_line,
    grade,
    impact_nodes,
    inferred_marker,
    main,
    no_c4,
    read_workspace,
    spec_and_adrs_only,
)
from evals.design_spec_grade import _run as run_command  # pyright: ignore[reportPrivateUsage]


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


@pytest.mark.parametrize("depth", [2, 3], ids=["in-the-repository", "in-mutmuts-copy"])
def test_find_evals_walks_up_to_the_nearest_design_spec(tmp_path: Path, depth: int) -> None:
    evals: Path = tmp_path / "design-spec" / "evals" / "evals.json"
    evals.parent.mkdir(parents=True)
    evals.write_text("{}", encoding="utf-8")
    module: Path = tmp_path.joinpath(*["sub"] * depth, "design_spec_grade.py")
    assert find_evals(module) == evals


def test_find_evals_names_the_start_when_no_ancestor_holds_design_spec(tmp_path: Path) -> None:
    module: Path = tmp_path / "evals" / "design_spec_grade.py"
    with pytest.raises(FileNotFoundError, match=r"design-spec/evals/evals\.json above .*design_spec_grade\.py"):
        find_evals(module)


def test_evals_is_found_from_this_module() -> None:
    assert find_evals(Path(sys.modules["evals.design_spec_grade"].__file__ or "")) == EVALS
    assert EVALS.is_file()


def test_rules_match_the_assertions_in_evals_json() -> None:
    document: dict[str, list[dict[str, object]]] = json.loads(EVALS.read_text(encoding="utf-8"))
    ids: set[object] = {entry["id"] for entry in document["evals"]}
    assert set(RULES) <= ids
    entry: dict[str, object]
    for entry in document["evals"]:
        bind(cast("list[str]", entry["assertions"]), RULES.get(cast("int", entry["id"]), ()))


@pytest.mark.parametrize("eval_id", [1, 3, 4, 5, 6])
def test_every_eval_that_writes_a_spec_grades_its_diagrams(eval_id: int) -> None:
    checks: list[Check] = [rule.check for rule in RULES[eval_id]]
    assert diagrams_parse in checks
    assert no_c4 in checks


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


DESIGN_HEADER: str = "| Boundary | Input | Output | Grain / key | Invariants | Owner |\n|---|---|---|---|---|---|\n"
DOCUMENT_HEADER: str = "| Boundary | Input | Output | Grain/key | Invariants | Owner | Source |\n|---|---|---|---|---|---|---|\n"


def _mermaid(*lines: str) -> str:
    """Return a fenced Mermaid block."""
    return "```mermaid\n" + "\n".join(lines) + "\n```\n"


@pytest.mark.parametrize(
    ("columns", "spec", "verdict"),
    [
        (
            DESIGN_COLUMNS,
            f"# Spec\n\n{DESIGN_HEADER}| CSV | rows | `Order` | one per order | typed | `io` |\n",
            Verdict(passed=True, evidence="contract table header is boundary | input | output | grain/key | invariants | owner"),
        ),
        (
            DOCUMENT_COLUMNS,
            DESIGN_HEADER,
            Verdict(
                passed=False,
                evidence="contract table header is boundary | input | output | grain/key | invariants | owner; expected boundary | input | output | grain/key | invariants | owner | source",
            ),
        ),
        (DESIGN_COLUMNS, "| Node | Source |\n|---|---|\n| Cli | `cli.py:1` |\n", Verdict(passed=False, evidence="no contract table (a table whose first column is Boundary)")),
        (DESIGN_COLUMNS, f"```markdown\n{DESIGN_HEADER}```\n", Verdict(passed=False, evidence="no contract table (a table whose first column is Boundary)")),
        (
            DOCUMENT_COLUMNS,
            f"   ```markdown\n{DESIGN_HEADER}   ```\n\n{DOCUMENT_HEADER}",
            Verdict(passed=True, evidence="contract table header is boundary | input | output | grain/key | invariants | owner | source"),
        ),
    ],
    ids=["design-columns", "missing-source", "no-contract-table", "table-in-a-fence", "table-in-an-indented-fence"],
)
def test_contract_header(columns: tuple[str, ...], spec: str, verdict: Verdict) -> None:
    assert contract_header(columns)(_run(spec=spec)) == verdict


def test_contract_header_takes_the_first_contract_table() -> None:
    spec: str = f"{DESIGN_HEADER}| a | b | c | d | e | f |\n\ntext\n\n{DOCUMENT_HEADER}"
    assert contract_header(DESIGN_COLUMNS)(_run(spec=spec)).passed is True


def test_contract_sources_passes_when_every_row_cites_a_line() -> None:
    spec: str = (
        f"{DOCUMENT_HEADER}| Config | JSON | `Config` | one per run | schema | `plan` | `src/config.py:12`, `src/semantics.py:3` |\n| Plan | `Config` | `Plan` | one per sheet | fits | `plan` | `src/plan.py:7` |\n"
    )
    assert contract_sources(_run(spec=spec)) == Verdict(passed=True, evidence="contract table header is boundary | input | output | grain/key | invariants | owner | source; all 2 rows cite a path:line source")


def test_contract_sources_names_rows_without_a_line() -> None:
    spec: str = f"{DOCUMENT_HEADER}| Config | JSON | `Config` | one per run | schema | `plan` | `src/config.py` |\n| Plan | `Config` | `Plan` | one per sheet | fits | `plan` |\n| Write | `Plan` | files | one per file | local | `excel` | `src/w.py:4` |\n"
    assert contract_sources(_run(spec=spec)) == Verdict(passed=False, evidence="contract rows without a path:line source: Config, Plan")


@pytest.mark.parametrize("spec", [DESIGN_HEADER, None], ids=["design-header", "no-spec"])
def test_contract_sources_fails_without_the_document_header(spec: str | None) -> None:
    run: Run = _run(spec=spec)
    assert contract_sources(run) == contract_header(DOCUMENT_COLUMNS)(run)
    assert contract_sources(run).passed is False


def test_table_cells_keep_escaped_pipes() -> None:
    spec: str = f"{DOCUMENT_HEADER}| a \\| b | c | d | e | f | g | `x.py:1` |\n"
    assert contract_sources(_run(spec=spec)).passed is True


@pytest.mark.parametrize(
    ("text", "found"),
    [
        ("`packages/pqx-report/src/pqx_report/model.py:17`", [("packages/pqx-report/src/pqx_report/model.py", "17")]),
        ("(`CLAUDE.md:97`) and run.py:348.", [("CLAUDE.md", "97"), ("run.py", "348")]),
        ("lines `a/b.py:10-20` and col `c.py:3:5`", [("a/b.py", "10"), ("c.py", "3")]),
        ("at 08:00:00, ratio 16:9, host 127.0.0.1:8080, sum mod 2^128", []),
        ("see https://example.com/x.py:12 and node:22", []),
        ("Common:::inferred and `docs/design.md`", []),
    ],
    ids=["backticked", "bare", "range-and-column", "numbers", "urls-and-schemes", "not-citations"],
)
def test_citation_pattern(text: str, found: list[tuple[str, str]]) -> None:
    assert CITATION.findall(text) == found


@pytest.mark.parametrize(
    ("spec", "verdict"),
    [
        (_mermaid("flowchart LR", "    A --> B"), Verdict(passed=True, evidence="no Mermaid C4 diagram")),
        (_mermaid("%% context", "C4Component", "  Person(a, 'A')") + _mermaid("  C4Deployment"), Verdict(passed=False, evidence="Mermaid C4 diagrams used: C4Component, C4Deployment")),
        ("C4Component named in prose is not a diagram\n", Verdict(passed=True, evidence="no Mermaid C4 diagram")),
        (_mermaid("flowchart LR", "  C4Gateway --> B"), Verdict(passed=True, evidence="no Mermaid C4 diagram")),
    ],
    ids=["flowchart", "c4-blocks", "prose", "node-named-c4"],
)
def test_no_c4(spec: str, verdict: Verdict) -> None:
    assert no_c4(_run(spec=spec)) == verdict


@pytest.mark.parametrize(
    ("spec", "passed"),
    [
        (_mermaid("flowchart LR", "  A:::added", "  classDef added fill:#dafbe1", "  classDef changed fill:#fff8c5", "  classDef removed fill:#ffebe9"), True),
        (_mermaid("%% impact", "graph TD", "  A --> B", "  class A,B changed", "  classDef added,changed fill:#eee", "  classDef removed fill:#fee"), True),
        (_mermaid("flowchart LR", "  A:::removed", "  classDef added fill:#dafbe1", "  classDef changed fill:#fff8c5") + _mermaid("flowchart LR", "  classDef removed fill:#fee"), False),
        (_mermaid("stateDiagram-v2", "  A:::added", "  classDef added fill:#a", "  classDef changed fill:#b", "  classDef removed fill:#c"), False),
        (_mermaid("flowchart LR", "  classDef added fill:#a", "  classDef changed fill:#b", "  classDef removed fill:#c"), False),
        (_mermaid(""), False),
    ],
    ids=["one-flowchart", "graph-class-statement-and-comma-list", "split-across-diagrams", "not-a-flowchart", "no-node-styled", "empty-block"],
)
def test_change_classdefs(spec: str, *, passed: bool) -> None:
    assert change_classdefs(_run(spec=spec)) == Verdict(
        passed=passed,
        evidence="a flowchart defines classDef added, changed and removed and styles nodes with them" if passed else "no flowchart defines classDef added, changed and removed and styles a node with one",
    )


DASHED: str = "  classDef inferred stroke:#555,stroke-dasharray:5 5"


@pytest.mark.parametrize(
    ("spec", "verdict"),
    [
        (
            _mermaid("flowchart LR", '  A["a ?"]:::inferred', "  B[b]", DASHED) + _mermaid("stateDiagram-v2", "  S: s ?", "  class S inferred", "  classDef inferred stroke-dasharray:3"),
            Verdict(passed=True, evidence="diagrams applying the inferred class: 2, each defining classDef inferred dashed"),
        ),
        (_mermaid("flowchart LR", '  A["a ?"]', "  classDef other stroke-dasharray:5 5"), Verdict(passed=True, evidence="no diagram applies the inferred class")),
        (_mermaid("flowchart LR", "  A:::inferred", "  classDef inferred stroke:#555"), Verdict(passed=False, evidence="diagram 1 applies the inferred class without classDef inferred stroke-dasharray")),
        (_mermaid("flowchart LR", "  A --> B") + _mermaid("flowchart LR", "  A:::inferred"), Verdict(passed=False, evidence="diagram 2 applies the inferred class without classDef inferred stroke-dasharray")),
    ],
    ids=["dashed-in-both-diagrams", "class-not-applied", "not-dashed", "class-not-defined"],
)
def test_inferred_marker(spec: str, verdict: Verdict) -> None:
    assert inferred_marker(_run(spec=spec)) == verdict


@pytest.mark.parametrize("check", [contract_header(DESIGN_COLUMNS), contract_sources, no_c4, change_classdefs, inferred_marker], ids=["header", "sources", "c4", "change", "inferred"])
def test_spec_checks_fail_without_a_spec(check: Check) -> None:
    assert check(_run(spec=None)) == Verdict(passed=False, evidence=f"no spec at {Path('fixture/docs/design.md')}")


def _graded(number: int, start: str, run: Run) -> Result:
    """Grade the assertion of eval ``number`` that starts with ``start``, with its rule in RULES."""
    rule: Rule = next(rule for rule in RULES[number] if rule.assertion.startswith(start))
    return grade([rule.assertion], [rule], run)[0]


DOCUMENT_SPEC: str = f"{DOCUMENT_HEADER}| Config | JSON | `Config` | one per run | schema | `plan` | `src/config.py:12` |\n"


@pytest.mark.parametrize(
    ("number", "start", "spec", "status"),
    [
        (1, "A boundary contract table", f"{DESIGN_HEADER}| CSV | rows | `Order` | one per order | typed | `io` |\n", "manual"),
        (1, "A boundary contract table", DOCUMENT_SPEC, "fail"),
        (1, "A context view drawn as a flowchart", _mermaid("flowchart LR", "  A --> B"), "manual"),
        (1, "A context view drawn as a flowchart", _mermaid("C4Dynamic"), "fail"),
        (3, "Every boundary in the contract table", DOCUMENT_SPEC, "manual"),
        (3, "Every boundary in the contract table", DESIGN_HEADER, "fail"),
        (5, "Every boundary in the contract table", DOCUMENT_SPEC, "manual"),
        (5, "Every boundary in the contract table", DESIGN_HEADER, "fail"),
        (5, "Items deduced rather than read", _mermaid("flowchart LR", "  A:::inferred", DASHED), "manual"),
        (5, "Items deduced rather than read", _mermaid("flowchart LR", "  A:::inferred"), "fail"),
        (6, "A change-impact flowchart", _mermaid("flowchart LR", "  Stage:::removed", "  classDef added fill:#a", "  classDef changed fill:#b", "  classDef removed fill:#c"), "pass"),
        (6, "A change-impact flowchart", _mermaid("flowchart LR", "  A --> B"), "fail"),
    ],
    ids=[
        "1-contract-header",
        "1-contract-header-wrong",
        "1-context-view",
        "1-context-view-c4",
        "3-contract-sources",
        "3-contract-sources-missing",
        "3b-contract-sources",
        "3b-contract-sources-missing",
        "3b-inferred",
        "3b-inferred-missing",
        "6-change-classdefs",
        "6-change-classdefs-missing",
    ],
)
def test_rules_decide_the_spec_assertions(number: int, start: str, spec: str, status: Status) -> None:
    assert _graded(number, start, _run(spec=spec)).status == status


def _git(cwd: Path, *args: str) -> str:
    """Run git in ``cwd`` with a fixed identity and no signing; return its output."""
    command: list[str] = ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false", *args]
    status: int
    output: str
    error: str
    status, output, error = run_command(command, cwd)
    assert status == 0, error
    return output.strip()


@pytest.fixture
def repo(tmp_path: Path) -> tuple[Path, str]:
    """A git repository with one commit: three-line code, a one-line README without a newline, docs."""
    root: Path = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "docs").mkdir()
    (root / "src" / "app.py").write_text("a = 1\nb = 2\nc = 3\n", encoding="utf-8")
    (root / "README.md").write_text("tally", encoding="utf-8")
    (root / "docs" / "guide.md").write_text("# Guide\n", encoding="utf-8")
    (root / ".gitignore").write_text(".venv/\n", encoding="utf-8")
    _git(root, "init", "-q", "-b", "main")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "build")
    return root, _git(root, "rev-parse", "HEAD")


def _repo_run(repo: tuple[Path, str], spec: str | None = None, commit: str | None = None) -> Run:
    """Return run inputs for the repository fixture, at its build commit unless ``commit`` is given."""
    root: Path
    sha: str
    root, sha = repo
    return Run(fixture=root, commit=commit or sha, spec_path=root / "docs" / "design.md", spec=spec, reply=None)


def test_run_returns_status_and_both_streams_from_cwd(tmp_path: Path) -> None:
    status: int
    output: str
    error: str
    status, output, error = run_command([sys.executable, "-c", "import os, sys; print(os.getcwd()); sys.stderr.buffer.write('→'.encode())"], tmp_path)
    assert (status, output.strip(), error.strip()) == (0, str(tmp_path), "→")


def test_citations_exist_passes_when_every_line_is_there(repo: tuple[Path, str]) -> None:
    spec: str = "Rows (`src/app.py:1`, `src/app.py:3`) and README.md:1."
    assert citations_exist(_repo_run(repo, spec)) == Verdict(passed=True, evidence=f"all 3 cited path:line exist at {repo[1]}")


def test_citations_exist_names_each_missing_citation(repo: tuple[Path, str]) -> None:
    root: Path = repo[0]
    (root / "src" / "app.py").write_text("x = 1\n" * 10, encoding="utf-8")
    (root / "new.py").write_text("y = 1\n", encoding="utf-8")
    spec: str = "`src/app.py:5` changed after the build, `new.py:1` untracked, `README.md:2`, `src/app.py:0`, `src/:1` a folder, `src/app.py:2` fine"
    assert citations_exist(_repo_run(repo, spec)) == Verdict(
        passed=False,
        evidence=(
            f"5 of 6 citations do not exist at {repo[1]}: README.md:2 (README.md has 1 lines); new.py:1 (not tracked); src/:1 (not tracked); src/app.py:0 (src/app.py has 3 lines); src/app.py:5 (src/app.py has 3 lines)"
        ),
    )


def test_citations_exist_fails_a_spec_that_cites_nothing(repo: tuple[Path, str]) -> None:
    assert citations_exist(_repo_run(repo, "No citations here.")) == Verdict(passed=False, evidence="the spec cites no path:line")


def test_citations_exist_fails_an_unknown_build_commit(repo: tuple[Path, str]) -> None:
    assert citations_exist(_repo_run(repo, "`src/app.py:1`", commit="0" * 40)) == Verdict(passed=False, evidence=f"build commit {'0' * 40} is not a commit in {repo[0]}")


def test_citations_exist_fails_without_a_spec(repo: tuple[Path, str]) -> None:
    assert citations_exist(_repo_run(repo)) == Verdict(passed=False, evidence=f"no spec at {repo[0] / 'docs' / 'design.md'}")


def test_documentation_only_passes_a_clean_fixture(repo: tuple[Path, str]) -> None:
    assert documentation_only(_repo_run(repo)) == Verdict(passed=True, evidence=f"nothing changed since {repo[1]}")


def test_documentation_only_passes_documentation_changes(repo: tuple[Path, str]) -> None:
    root: Path = repo[0]
    (root / "docs" / "design.md").write_text("# Design\n", encoding="utf-8")
    (root / "docs" / "adr").mkdir()
    (root / "docs" / "adr" / "0001-x.md").write_text("# ADR\n", encoding="utf-8")
    (root / "README.md").write_text("tally, documented", encoding="utf-8")
    (root / ".venv").mkdir()
    (root / ".venv" / "ignored.py").write_text("", encoding="utf-8")
    assert documentation_only(_repo_run(repo)) == Verdict(passed=True, evidence=f"changed since {repo[1]}: README.md, docs/adr/0001-x.md, docs/design.md")


def test_documentation_only_names_code_changes_committed_staged_and_untracked(repo: tuple[Path, str]) -> None:
    root: Path = repo[0]
    (root / "src" / "app.py").write_text("a = 1\n", encoding="utf-8")
    _git(root, "commit", "-q", "-am", "after the build")
    (root / "staged.py").write_text("", encoding="utf-8")
    _git(root, "add", "staged.py")
    (root / "untracked.toml").write_text("", encoding="utf-8")
    (root / "docs" / "design.md").write_text("# Design\n", encoding="utf-8")
    assert documentation_only(_repo_run(repo)) == Verdict(passed=False, evidence="changed outside documentation files: src/app.py, staged.py, untracked.toml")


def test_documentation_only_names_a_staged_change_the_worktree_undoes(repo: tuple[Path, str]) -> None:
    root: Path = repo[0]
    (root / "src" / "app.py").write_text("a = 1\n", encoding="utf-8")
    (root / "added.py").write_text("", encoding="utf-8")
    _git(root, "add", "src/app.py", "added.py")
    _git(root, "restore", "--source=HEAD", "--worktree", "src/app.py")
    (root / "added.py").unlink()
    assert documentation_only(_repo_run(repo)) == Verdict(passed=False, evidence="changed outside documentation files: added.py, src/app.py")


def test_documentation_only_fails_when_git_cannot_compare(repo: tuple[Path, str]) -> None:
    verdict: Verdict = documentation_only(_repo_run(repo, commit="nope"))
    assert verdict.passed is False
    assert verdict.evidence.startswith("git diff --no-renames --name-only -z nope failed: ")


def test_spec_and_adrs_only_accepts_only_the_spec_and_adrs(tmp_path: Path) -> None:
    root: Path = tmp_path / "empty"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    run: Run = Run(fixture=root, commit=EMPTY_TREE, spec_path=root / "docs" / "design.md", spec=None, reply=None)
    assert spec_and_adrs_only(run) == Verdict(passed=True, evidence=f"nothing changed since {EMPTY_TREE}")
    (root / "docs" / "adr").mkdir(parents=True)
    (root / "docs" / "design.md").write_text("# Design\n", encoding="utf-8")
    (root / "docs" / "adr" / "0001-x.md").write_text("# ADR\n", encoding="utf-8")
    assert spec_and_adrs_only(run) == Verdict(passed=True, evidence=f"changed since {EMPTY_TREE}: docs/adr/0001-x.md, docs/design.md")
    (root / "docs" / "notes.md").write_text("notes\n", encoding="utf-8")
    (root / "main.py").write_text("", encoding="utf-8")
    (root / "docs" / "adr" / "helper.py").write_text("", encoding="utf-8")
    _git(root, "add", "main.py")
    assert spec_and_adrs_only(run) == Verdict(passed=False, evidence="changed outside docs/design.md and Markdown ADRs under docs/adr/: docs/adr/helper.py, docs/notes.md, main.py")


def test_documentation_only_names_code_under_docs(repo: tuple[Path, str]) -> None:
    (repo[0] / "docs" / "conf.py").write_text("", encoding="utf-8")
    assert documentation_only(_repo_run(repo)) == Verdict(passed=False, evidence="changed outside documentation files: docs/conf.py")


def test_documentation_only_names_both_sides_of_a_rename(repo: tuple[Path, str]) -> None:
    root: Path = repo[0]
    _git(root, "mv", "src/app.py", "docs/app.md")
    assert documentation_only(_repo_run(repo)) == Verdict(passed=False, evidence="changed outside documentation files: src/app.py")


@pytest.mark.parametrize(
    ("number", "start"),
    [
        (1, "No code is written: the only files added"),
        (3, "Every path:line the spec cites"),
        (3, "No code is changed"),
        (4, "Every path:line the spec cites"),
        (4, "No code is changed"),
        (5, "Every path:line the spec cites"),
        (5, "No code is changed"),
        (6, "No code is written"),
    ],
)
def test_rules_decide_the_fixture_assertions(repo: tuple[Path, str], number: int, start: str) -> None:
    root: Path = repo[0]
    assert _graded(number, start, _repo_run(repo, "Cites `src/app.py:2`.")).status == "pass"
    (root / "src" / "new.py").write_text("", encoding="utf-8")
    assert _graded(number, start, _repo_run(repo, "Cites `src/new.py:1`.")).status == "fail"


@dataclass
class FakeValidator:
    """Stand-in for ``_run`` that answers as validate_mermaid.mjs would and records each command."""

    status: int
    output: str
    error: str = ""
    calls: list[tuple[list[str], Path]] = field(default_factory=list[tuple[list[str], Path]])

    def __call__(self, command: list[str], cwd: Path) -> tuple[int, str, str]:
        """Record the call and return the canned result."""
        self.calls.append((command, cwd))
        return self.status, self.output, self.error


@pytest.mark.parametrize(
    ("fake", "verdict"),
    [
        (
            FakeValidator(0, "d.md: block 1 (line 20): OK flowchart-v2\nd.md: block 2 (line 40): OK stateDiagram\n"),
            Verdict(passed=True, evidence="validate_mermaid.mjs exit 0: 2 diagrams parse"),
        ),
        (FakeValidator(0, "d.md: no Mermaid diagrams\n"), Verdict(passed=True, evidence="validate_mermaid.mjs exit 0: 0 diagrams parse")),
        (
            FakeValidator(1, "d.md: block 1 (line 2): OK flowchart-v2\nd.md: block 2 (line 9): FAIL Error: Parse error on line 4\n"),
            Verdict(passed=False, evidence="validate_mermaid.mjs exit 1: d.md: block 2 (line 9): FAIL Error: Parse error on line 4"),
        ),
        (FakeValidator(2, "", "needs Node 22.22.2+\n"), Verdict(passed=None, evidence="validate_mermaid.mjs could not run (exit 2): needs Node 22.22.2+")),
        (
            FakeValidator(1, "", "Error: npm install failed in cache: ECONNREFUSED\n"),
            Verdict(passed=None, evidence="validate_mermaid.mjs could not run (exit 1): Error: npm install failed in cache: ECONNREFUSED"),
        ),
    ],
    ids=["parse", "no-diagrams", "parse-error", "cannot-run", "crash-before-parsing"],
)
def test_diagrams_parse_reports_the_checker(monkeypatch: pytest.MonkeyPatch, fake: FakeValidator, verdict: Verdict) -> None:
    # A fresh copy: parametrize builds ``fake`` once per process, and mutmut runs the suite more than once in one.
    validator: FakeValidator = replace(fake, calls=[])
    monkeypatch.setattr("evals.design_spec_grade._run", validator)
    run: Run = _run(spec="# Spec\n")
    assert diagrams_parse(run) == verdict
    assert validator.calls == [(["node", str(VALIDATOR), str(run.spec_path)], VALIDATOR.parent)]
    assert VALIDATOR.is_file()


def test_diagrams_parse_fails_without_a_spec() -> None:
    assert diagrams_parse(_run(spec=None)) == Verdict(passed=False, evidence=f"no spec at {Path('fixture/docs/design.md')}")


def test_run_reports_a_missing_program_as_exit_127(tmp_path: Path) -> None:
    status: int
    output: str
    error: str
    status, output, error = run_command(["no-such-program-for-the-grader"], tmp_path)
    assert (status, output) == (127, "")
    assert error


@pytest.mark.parametrize(("number", "status"), [(1, "pass"), (6, "pass")])
def test_rules_run_the_diagram_checker(monkeypatch: pytest.MonkeyPatch, number: int, status: Status) -> None:
    monkeypatch.setattr("evals.design_spec_grade._run", FakeValidator(0, "d.md: block 1 (line 2): OK flowchart-v2\n"))
    assert _graded(number, "Every Mermaid diagram in the spec passes", _run(spec="# Spec\n")).status == status


SHOP: Workspace = Workspace(
    packages=(
        Package("shop-common", frozenset({"shop_common"}), frozenset()),
        Package("shop-core", frozenset({"shop_core"}), frozenset({"shop-common"})),
        Package("shop-io", frozenset({"shop_io"}), frozenset({"shop-common", "shop-core"})),
        Package("shop-cli", frozenset({"shop_cli"}), frozenset({"shop-common", "shop-io"})),
    ),
    imports=frozenset({("shop-core", "shop-common"), ("shop-io", "shop-common"), ("shop-cli", "shop-common"), ("shop-cli", "shop-io"), ("shop-cli", "shop-core")}),
    modules=frozenset({"shop_common", "shop_common.types", "shop_core", "shop_io", "shop_cli"}),
)
"""A workspace whose CLI imports core undeclared and whose io declares core unused."""


def _matrix(*rows: str) -> str:
    """Return a dependency matrix over SHOP's packages, one ``| label | cells |`` row per argument."""
    return "| imports ↓ / of → | common | core | io | cli |\n|---|---|---|---|---|\n" + "".join(f"{row}\n" for row in rows)


SHOP_MATRIX: str = _matrix("| common | | | | |", "| core | Y | | | |", "| io | Y | **d** | | |", "| cli | Y | **!** | Y | |")


@dataclass
class FakeReader:
    """Stand-in for ``read_workspace`` that returns a canned workspace and records each run."""

    answer: Workspace | Verdict
    runs: list[Run] = field(default_factory=list[Run])

    def __call__(self, run: Run) -> Workspace | Verdict:
        """Record the run and return the canned answer."""
        self.runs.append(run)
        return self.answer


@pytest.mark.parametrize(
    ("cells", "spec", "verdict"),
    [
        ((("cli", "core"),), SHOP_MATRIX, Verdict(passed=True, evidence="the dependency matrix equals the code's at abc1234 (4 packages, 4 Y cells): cli → core !, io → core d")),
        ((), SHOP_MATRIX, Verdict(passed=True, evidence="the dependency matrix equals the code's at abc1234 (4 packages, 4 Y cells): cli → core !, io → core d")),
        (
            (("shop-cli", "shop-core"),),
            _matrix("| core | Y | | | |", "| io | Y | d | | |", "| cli | Y | Y | Y | |"),
            Verdict(passed=False, evidence="the dependency matrix differs from the code at abc1234 where the assertion looks: cli → core is Y in the spec, ! in the code"),
        ),
        (
            (("cli", "core"),),
            _matrix("| core | Y | | | |", "| io | Y | | | |", "| cli | Y | Y | Y | |"),
            Verdict(
                passed=False,
                evidence="the dependency matrix differs from the code at abc1234 where the assertion looks: cli → core is Y in the spec, ! in the code; and elsewhere: io → core is blank in the spec, d in the code",
            ),
        ),
        (
            (("cli", "core"), ("io", "core")),
            _matrix("| core | Y | | | |", "| io | | d | | |", "| cli | Y | ! | Y | |"),
            Verdict(passed=True, evidence="the named cells agree with the code at abc1234 (cli → core !, io → core d); the rest of the matrix differs: io → common is blank in the spec, Y in the code"),
        ),
        (
            (),
            _matrix("| core | Y | | | |", "| io | Y | | | |", "| cli | Y | ! | Y | |"),
            Verdict(passed=None, evidence="the dependency matrix differs from the code at abc1234: io → core is blank in the spec, d in the code"),
        ),
    ],
    ids=["equal", "equal-no-cells", "named-cell-differs", "named-and-other-cells-differ", "other-cell-differs", "differs-no-cells"],
)
def test_dependency_matrix_compares_the_spec_with_the_code(cells: tuple[tuple[str, str], ...], spec: str, verdict: Verdict) -> None:
    reader: FakeReader = FakeReader(SHOP)
    run: Run = _run(spec=spec)
    assert dependency_matrix(reader, *cells)(run) == verdict
    assert reader.runs == [run]


def test_dependency_matrix_reads_labels_as_package_or_module_names() -> None:
    spec: str = "| Imports | `shop-common` | shop_core | **io** | cli |\n|---|---|---|---|---|\n| Shop-Core | `Y` | — | | |\n| shop_io | Y | *d* | — | |\n| `cli` | Y | ! | Y | — |\n| shop-web | Y | | | |\n"
    assert dependency_matrix(FakeReader(SHOP), ("cli", "core"))(_run(spec=spec)) == Verdict(
        passed=True, evidence="the named cells agree with the code at abc1234 (cli → core !); the rest of the matrix differs: shop-web → common is Y in the spec, blank in the code"
    )


def test_dependency_matrix_reads_the_first_matrix_and_ignores_short_rows() -> None:
    spec: str = f"| Cell | Source |\n|---|---|\n| cli → core | `x.py:1` |\n\n{_matrix('| core | Y |', '| io | Y | d |', '| cli | Y | ! | Y |')}\n{_matrix('| cli | | | | |')}"
    assert dependency_matrix(FakeReader(SHOP))(_run(spec=spec)).passed is True


@pytest.mark.parametrize(("cells", "passed"), [((("cli", "core"),), False), ((), None)], ids=["named-cells-fail", "no-cells-manual"])
def test_dependency_matrix_without_a_matrix(cells: tuple[tuple[str, str], ...], *, passed: bool | None) -> None:
    no_table: Verdict = dependency_matrix(FakeReader(SHOP), *cells)(_run(spec="# Spec\n\nNo matrix.\n"))
    assert no_table == Verdict(passed=passed, evidence="no dependency matrix (a table whose first header cell starts with 'imports')")
    no_spec: Verdict = dependency_matrix(FakeReader(SHOP), *cells)(_run(spec=None))
    assert no_spec == Verdict(passed=passed, evidence=f"no spec at {Path('fixture/docs/design.md')}")


def test_dependency_matrix_names_packages_in_neither_a_row_nor_a_column() -> None:
    docs: Package = Package("shop-docs", frozenset({"shop_docs"}), frozenset())
    workspace: Workspace = replace(SHOP, packages=(*SHOP.packages, docs))
    spec: str = "| imports | common | core | io |\n|---|---|---|---|\n| core | Y | | |\n| io | Y | d | |\n| cli | Y | ! | Y |\n"
    assert dependency_matrix(FakeReader(workspace))(_run(spec=spec)) == Verdict(
        passed=True, evidence="the dependency matrix equals the code's at abc1234 (5 packages, 4 Y cells): cli → core !, io → core d; not in the matrix: docs"
    )


def test_workspace_matrix_leaves_imports_within_a_package_out() -> None:
    workspace: Workspace = replace(SHOP, imports=SHOP.imports | {("shop-io", "shop-io")})
    assert workspace.matrix() == SHOP.matrix()


def test_dependency_matrix_decides_nothing_when_the_code_cannot_be_read() -> None:
    unreadable: Verdict = Verdict(passed=None, evidence="git archive failed")
    assert dependency_matrix(FakeReader(unreadable), ("cli", "core"))(_run(spec=SHOP_MATRIX)) == unreadable


type Tree = dict[str, tuple[list[str], dict[str, str]]]
"""Workspace packages by name: their declared dependencies, and their files under ``src/`` with contents."""


def _workspace_repo(root: Path, packages: Tree) -> str:
    """Write a uv-workspace-shaped repository under ``root``, commit it, and return the commit."""
    name: str
    dependencies: list[str]
    files: dict[str, str]
    for name, (dependencies, files) in packages.items():
        folder: Path = root / "packages" / name
        folder.mkdir(parents=True)
        listed: str = ", ".join(f'"{dependency}"' for dependency in dependencies)
        (folder / "pyproject.toml").write_text(f'[project]\nname = "{name}"\nversion = "0.1.0"\ndependencies = [{listed}]\n', encoding="utf-8")
        path: str
        content: str
        for path, content in files.items():
            (folder / "src" / path).parent.mkdir(parents=True, exist_ok=True)
            (folder / "src" / path).write_text(content, encoding="utf-8")
    _git(root, "init", "-q", "-b", "main")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "build")
    return _git(root, "rev-parse", "HEAD")


SHOP_TREE: Tree = {
    "shop-common": ([], {"shop_common/__init__.py": "", "shop_common/types.py": "X = 1\n"}),
    "shop-core": (["shop-common"], {"shop_core/__init__.py": "from shop_common.types import X\n"}),
    "shop-io": (["shop-common", "Shop_Core>=0.1", "polars[pyarrow]>=1"], {"shop_io/__init__.py": "import shop_common\n"}),
    "shop-cli": (["shop-common", "shop-io"], {"shop_cli/__init__.py": "from typing import TYPE_CHECKING\n\nimport shop_common\nimport shop_io\n\nif TYPE_CHECKING:\n    import shop_core\n"}),
}
"""SHOP as code: cli's import of core is TYPE_CHECKING only, which the matrix still counts."""


def _shop_run(root: Path, commit: str) -> Run:
    """Return run inputs for a workspace repository at ``commit``."""
    return Run(fixture=root, commit=commit, spec_path=root / "docs" / "design.md", spec=None, reply=None)


def test_read_workspace_reads_packages_declarations_and_imports_at_the_build_commit(tmp_path: Path) -> None:
    commit: str = _workspace_repo(tmp_path, SHOP_TREE)
    (tmp_path / "packages" / "shop-common" / "src" / "shop_common" / "__init__.py").write_text("import shop_cli\n", encoding="utf-8")
    path: list[str] = list(sys.path)
    assert read_workspace(_shop_run(tmp_path, commit)) == Workspace(
        packages=(
            Package("shop-cli", frozenset({"shop_cli"}), frozenset({"shop-common", "shop-io"})),
            Package("shop-common", frozenset({"shop_common"}), frozenset()),
            Package("shop-core", frozenset({"shop_core"}), frozenset({"shop-common"})),
            Package("shop-io", frozenset({"shop_io"}), frozenset({"shop-common", "shop-core", "polars"})),
        ),
        imports=SHOP.imports,
        modules=SHOP.modules,
    )
    assert sys.path == path


def test_read_workspace_reads_only_package_source(tmp_path: Path) -> None:
    tree: Tree = {
        "app-base": ([], {"app_base/__init__.py": "", "loose.py": "import app_top\n"}),
        "app-top": (["app-base"], {"app_top/__init__.py": "import app_base\n"}),
        "app-empty": (["app-top"], {}),
    }
    _workspace_repo(tmp_path, tree)
    (tmp_path / "packages" / "app-base" / "tests").mkdir()
    (tmp_path / "packages" / "app-base" / "tests" / "test_base.py").write_text("import app_top\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "tests")
    workspace: Workspace | Verdict = read_workspace(_shop_run(tmp_path, _git(tmp_path, "rev-parse", "HEAD")))
    assert isinstance(workspace, Workspace)
    assert workspace.matrix() == {("app-top", "app-base"): "Y", ("app-empty", "app-top"): "d"}


def test_read_workspace_needs_a_build_commit(tmp_path: Path) -> None:
    _workspace_repo(tmp_path, SHOP_TREE)
    verdict: Workspace | Verdict = read_workspace(_shop_run(tmp_path, "0" * 40))
    assert isinstance(verdict, Verdict)
    assert verdict.passed is None
    assert verdict.evidence.startswith(f"git archive {'0' * 40} failed: ")


def test_read_workspace_needs_workspace_packages(tmp_path: Path) -> None:
    commit: str = _workspace_repo(tmp_path, {"app-docs": ([], {})})
    assert read_workspace(_shop_run(tmp_path, commit)) == Verdict(passed=None, evidence=f"no workspace packages with code under packages/*/src at {commit}")


PQX_TREE: Tree = {
    "pqx-common": ([], {"pqx_common/__init__.py": "", "pqx_common/names.py": "from pqx_excel import workbook\n"}),
    "pqx-excel": (["pqx-common"], {"pqx_excel/__init__.py": "", "pqx_excel/workbook.py": "from pqx_common import names\n"}),
    "pqx-frame": ([], {"pqx_frame/__init__.py": ""}),
    "pqx-plan": ([], {"pqx_plan/__init__.py": ""}),
    "pqx-verify": ([], {"pqx_verify/__init__.py": ""}),
    "pqx-report": (["pqx-plan", "pqx-verify"], {"pqx_report/__init__.py": "import pqx_frame\n"}),
}
"""Eval 3's report defect and eval 4's reversed import, in miniature."""


def _pqx_matrix(common: str, report_frame: str) -> str:
    """Return a matrix over PQX_TREE with the given common row and report → frame cell."""
    return f"| imports ↓ / of → | common | excel | frame | plan | verify |\n|---|---|---|---|---|---|\n| common | {common} |\n| excel | Y | | | | |\n| report | | | {report_frame} | d | d |\n"


@pytest.mark.parametrize(
    ("number", "start", "spec", "status"),
    [
        (3, "The dependency matrix marks", _pqx_matrix("| !", "**!**"), "manual"),
        (3, "The dependency matrix marks", _pqx_matrix("| !", "Y"), "fail"),
        (3, "The dependency matrix marks", _pqx_matrix("|", "!"), "manual"),
        (4, "The resynced dependency matrix", _pqx_matrix("| !", "!"), "manual"),
        (4, "The resynced dependency matrix", _pqx_matrix("|", "!"), "fail"),
        (4, "The resynced dependency matrix", _pqx_matrix("| !", "Y"), "manual"),
        (5, "All six defects", _pqx_matrix("| !", "!"), "manual"),
        (5, "All six defects", _pqx_matrix("|", "!"), "manual"),
    ],
    ids=["3", "3-report-wrong", "3-other-cell-wrong", "4", "4-reversed-import-missing", "4-other-cell-wrong", "3b-equal", "3b-differs"],
)
def test_rules_decide_the_matrix_assertions(tmp_path: Path, number: int, start: str, spec: str, status: Status) -> None:
    commit: str = _workspace_repo(tmp_path, PQX_TREE)
    run: Run = replace(_shop_run(tmp_path, commit), spec=spec)
    assert _graded(number, start, run).status == status


IMPACT_CLASSES: tuple[str, ...] = ("  classDef added fill:#dafbe1", "  classDef changed fill:#fff8c5", "  classDef removed fill:#ffebe9")


def test_impact_nodes_pass_when_each_names_what_the_code_has_or_lacks() -> None:
    spec: str = _mermaid(
        "flowchart LR",
        '  Cli["shop-cli: calls the typed record"]:::changed --> Core["`**shop_core**`"]',
        '  Types["shop_common.types"] --> Rec["shop_core.records ?"]:::added',
        "  Io --> Web",
        "  class Core,Types changed",
        "  Io[shop-io.]:::removed",
        *IMPACT_CLASSES,
    )
    reader: FakeReader = FakeReader(SHOP)
    run: Run = _run(spec=spec)
    assert impact_nodes(reader)(run) == Verdict(
        passed=True,
        evidence="at abc1234, changed and removed nodes name existing packages or modules, and added nodes new ones: shop-cli changed, shop_core changed, shop_common.types changed, shop_core.records added, shop-io removed",
    )
    assert reader.runs == [run]


def test_impact_nodes_name_each_node_that_does_not() -> None:
    spec: str = _mermaid(
        "graph TD",
        '  Ui["web ui"]:::changed',
        "  ShopIo:::removed",
        '  New(["shop_common"]):::added',
        '  Rec["Typed record"]:::added',
        "  shop_cli:::changed",
        '  Num["42"]:::changed',
        *IMPACT_CLASSES,
    )
    assert impact_nodes(FakeReader(SHOP))(_run(spec=spec)) == Verdict(
        passed=False,
        evidence=(
            "at abc1234: Ui (changed) names 'web', which is not a package or module; ShopIo (removed) names 'ShopIo', which is not a package or module; "
            "New (added) names 'shop_common', which already exists; Rec (added) names 'Typed', which is not written as a package or module; "
            "Num (changed) names '\"42\"', which is not a package or module"
        ),
    )


@pytest.mark.parametrize(
    "spec",
    [
        _mermaid("flowchart LR", "  A --> B", *IMPACT_CLASSES) + _mermaid("stateDiagram-v2", "  S:::added", *IMPACT_CLASSES),
        _mermaid("flowchart LR", "  A:::inferred", "  class B other"),
    ],
    ids=["no-flowchart-node-styled", "other-classes"],
)
def test_impact_nodes_fail_without_a_styled_node(spec: str) -> None:
    reader: FakeReader = FakeReader(SHOP)
    assert impact_nodes(reader)(_run(spec=spec)) == Verdict(passed=False, evidence="no flowchart node is styled added, changed or removed")
    assert reader.runs == []


def test_impact_nodes_ignore_commented_out_nodes() -> None:
    spec: str = _mermaid("flowchart LR", '  %% Ghost["shop-web"]:::removed', "  A[shop-io]:::changed", "  %%A:::removed", *IMPACT_CLASSES)
    assert impact_nodes(FakeReader(SHOP))(_run(spec=spec)) == Verdict(passed=True, evidence="at abc1234, changed and removed nodes name existing packages or modules, and added nodes new ones: shop-io changed")
    assert impact_nodes(FakeReader(SHOP))(_run(spec=_mermaid("flowchart LR", '  %% Ghost["shop-web"]:::removed', *IMPACT_CLASSES))) == Verdict(
        passed=False, evidence="no flowchart node is styled added, changed or removed"
    )


def test_impact_nodes_read_labels_from_shape_objects() -> None:
    spec: str = _mermaid(
        "flowchart LR",
        '  Real@{ shape: rect, label: "shop-io" }',
        "  Other@{ label: 'shop_core.records', shape: rect }",
        "  Bare@{ label: shop_core }",
        "  Real --> Other",
        "  class Real,Bare changed",
        "  class Other added",
        *IMPACT_CLASSES,
    )
    assert impact_nodes(FakeReader(SHOP))(_run(spec=spec)) == Verdict(
        passed=True, evidence="at abc1234, changed and removed nodes name existing packages or modules, and added nodes new ones: shop-io changed, shop_core.records added, shop_core changed"
    )


def test_impact_nodes_read_nodes_as_mermaid_does() -> None:
    """Mermaid keeps a dotted ID whole, shows a node's last label, and reads statements after a semicolon."""
    spec: str = _mermaid(
        "flowchart LR",
        "  shop_common.types:::changed",
        "  A[shop-io]; class A changed;",
        "  A[shop-web]",
        "  B[shop-web]:::removed",
        "  B[shop-io]",
        *IMPACT_CLASSES,
    )
    assert impact_nodes(FakeReader(SHOP))(_run(spec=spec)) == Verdict(passed=False, evidence="at abc1234: A (changed) names 'shop-web', which is not a package or module")


def test_impact_nodes_accept_a_code_named_id_for_changed_and_removed_nodes() -> None:
    spec: str = _mermaid(
        "flowchart LR",
        '  shop_core["Core (shop_core): returns a typed record"]:::changed',
        '  shop_io["shop_io.records"]:::added',
        '  Cli["Cli (shop-cli)"]:::removed',
        '  shop_cli["shop-web: handles requests"]:::changed',
        '  shop_common["Shop-Web: UI"]:::changed',
        *IMPACT_CLASSES,
    )
    assert impact_nodes(FakeReader(SHOP))(_run(spec=spec)) == Verdict(
        passed=False,
        evidence=(
            "at abc1234: Cli (removed) names 'Cli', which is not a package or module; shop_cli (changed) names 'shop-web', which is not a package or module; "
            "shop_common (changed) names 'Shop-Web', which is not a package or module"
        ),
    )
    passing: str = spec.split('  Cli["Cli (shop-cli)"]', maxsplit=1)[0] + "\n".join(IMPACT_CLASSES) + "\n```\n"
    assert impact_nodes(FakeReader(SHOP))(_run(spec=passing)) == Verdict(
        passed=True, evidence="at abc1234, changed and removed nodes name existing packages or modules, and added nodes new ones: shop_core changed, shop_io.records added"
    )


def test_impact_nodes_fail_without_a_spec() -> None:
    assert impact_nodes(FakeReader(SHOP))(_run(spec=None)) == Verdict(passed=False, evidence=f"no spec at {Path('fixture/docs/design.md')}")


def test_impact_nodes_decide_nothing_when_the_code_cannot_be_read() -> None:
    unreadable: Verdict = Verdict(passed=None, evidence="git archive failed")
    assert impact_nodes(FakeReader(unreadable))(_run(spec=_mermaid("flowchart LR", "  A[shop-io]:::changed"))) == unreadable


@pytest.mark.parametrize(
    ("node", "status"),
    [('  New["pqx_common.records"]:::added', "pass"), ('  Gone["pqx-gone"]:::removed', "fail")],
    ids=["existing-and-new", "removed-missing"],
)
def test_rules_decide_the_impact_nodes_assertion(tmp_path: Path, node: str, status: Status) -> None:
    commit: str = _workspace_repo(tmp_path, PQX_TREE)
    spec: str = _mermaid("flowchart LR", '  Common["pqx-common"]:::changed', node, *IMPACT_CLASSES)
    assert _graded(6, "Every changed or removed node names", replace(_shop_run(tmp_path, commit), spec=spec)).status == status
