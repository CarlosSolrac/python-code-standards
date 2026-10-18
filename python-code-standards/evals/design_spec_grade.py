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
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, TypedDict, cast

GRADER_VERSION: str = "1.0.0"
"""Bump on any change to what is graded, so grades from different versions are not compared."""

EVALS: Path = Path(__file__).resolve().parents[2] / "design-spec" / "evals" / "evals.json"
"""The design-spec evals whose assertions are graded."""

VALIDATOR: Path = EVALS.parents[1] / "skill" / "tools" / "validate_mermaid.mjs"
"""design-spec's own diagram checker: Mermaid's parser on every Mermaid block."""

EMPTY_TREE: str = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
"""Git's empty tree: eval 1's fixture has no commit, so its changes are compared with nothing."""

CLOSING: str = "Approve or correct before I implement."
"""The line a design-mode reply ends with (design-spec SKILL.md section 3)."""

DESIGN_COLUMNS: tuple[str, ...] = ("boundary", "input", "output", "grain/key", "invariants", "owner")
"""The boundary contract table's columns in design mode (design-spec SKILL.md section 3)."""

DOCUMENT_COLUMNS: tuple[str, ...] = (*DESIGN_COLUMNS, "source")
"""Document mode adds ``source``, the code that defines the output and enforces the invariants."""

CITATION: re.Pattern[str] = re.compile(r"(?<![\w./:-])((?=[\w./-]*[A-Za-z])[\w.-]*[./][\w./-]*):(\d+)\b")
"""A ``path:line`` citation: a path holding a letter and a dot or slash, a colon, a line number."""

_FENCE: re.Pattern[str] = re.compile(r"^ {0,3}```.*?^ {0,3}```[ \t]*$", re.MULTILINE | re.DOTALL)
_MERMAID: re.Pattern[str] = re.compile(r"```mermaid[ \t]*\r?\n([\s\S]*?)```")
_CLASSDEF: re.Pattern[str] = re.compile(r"^\s*classDef\s+(\S+)\s*(.*)$", re.MULTILINE)
_SEPARATOR: re.Pattern[str] = re.compile(r"^[\s|:-]+$")
_APPLIED: re.Pattern[str] = re.compile(r":::([\w-]+)|^\s*class\s+\S+\s+([\w-]+)", re.MULTILINE)

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


def contract_header(columns: Sequence[str]) -> Check:
    """Return a check that the boundary contract table's header is exactly ``columns``."""

    def check(run: Run) -> Verdict:
        table: list[list[str]] | Verdict = _contract_table(run)
        if isinstance(table, Verdict):
            return table
        return _header(table, columns)

    return check


def contract_sources(run: Run) -> Verdict:
    """Check the document-mode contract table: its header, and a ``path:line`` in every row's source."""
    table: list[list[str]] | Verdict = _contract_table(run)
    if isinstance(table, Verdict):
        return table
    header: Verdict = _header(table, DOCUMENT_COLUMNS)
    if not header.passed:
        return header
    uncited: list[str] = [row[0] for row in table[1:] if len(row) != len(DOCUMENT_COLUMNS) or not CITATION.search(row[-1])]
    if uncited:
        return Verdict(passed=False, evidence=f"contract rows without a path:line source: {', '.join(uncited)}")
    return Verdict(passed=True, evidence=f"{header.evidence}; all {len(table) - 1} rows cite a path:line source")


def no_c4(run: Run) -> Verdict:
    """Check that no Mermaid block is a C4 diagram: its type, not a node name, starts with ``C4``."""
    if run.spec is None:
        return _no_spec(run)
    found: list[str] = [kind for kind in map(_diagram_type, _MERMAID.findall(run.spec)) if kind.startswith("C4")]
    if found:
        return Verdict(passed=False, evidence=f"Mermaid C4 diagrams used: {', '.join(found)}")
    return Verdict(passed=True, evidence="no Mermaid C4 diagram")


def change_classdefs(run: Run) -> Verdict:
    """Check that one flowchart defines ``classDef added``, ``changed`` and ``removed`` and styles a node with one."""
    if run.spec is None:
        return _no_spec(run)
    wanted: set[str] = {"added", "changed", "removed"}
    block: str
    for block in _MERMAID.findall(run.spec):
        if _diagram_type(block) in {"flowchart", "graph"} and wanted <= set(_classdefs(block)) and _applied(block) & wanted:
            return Verdict(passed=True, evidence="a flowchart defines classDef added, changed and removed and styles nodes with them")
    return Verdict(passed=False, evidence="no flowchart defines classDef added, changed and removed and styles a node with one")


def inferred_marker(run: Run) -> Verdict:
    """Check that every diagram applying the ``inferred`` class defines it with a dashed border.

    That is the one part of SKILL.md section 7's marker a tool can decide. Which
    nodes are inferred, their `` ?`` labels, and the one-line note that may replace
    the marker above a fully inferred diagram are left to a person.
    """
    if run.spec is None:
        return _no_spec(run)
    marked: int = 0
    number: int
    block: str
    for number, block in enumerate(_MERMAID.findall(run.spec), start=1):
        if "inferred" not in _applied(block):
            continue
        if "stroke-dasharray" not in _classdefs(block).get("inferred", ""):
            return Verdict(passed=False, evidence=f"diagram {number} applies the inferred class without classDef inferred stroke-dasharray")
        marked += 1
    if not marked:
        return Verdict(passed=True, evidence="no diagram applies the inferred class")
    return Verdict(passed=True, evidence=f"diagrams applying the inferred class: {marked}, each defining classDef inferred dashed")


def diagrams_parse(run: Run) -> Verdict:
    """Check every Mermaid block with ``validate_mermaid.mjs``; a checker that cannot run decides nothing."""
    if run.spec is None:
        return _no_spec(run)
    status: int
    output: str
    error: str
    status, output, error = _run(["node", str(VALIDATOR), str(run.spec_path)], VALIDATOR.parent)
    if status == 0:
        return Verdict(passed=True, evidence=f"validate_mermaid.mjs exit 0: {output.count(': OK ')} diagrams parse")
    if status == 1:
        return Verdict(passed=False, evidence=f"validate_mermaid.mjs exit 1: {'; '.join(line for line in output.splitlines() if ': FAIL ' in line)}")
    return Verdict(passed=None, evidence=f"validate_mermaid.mjs could not run (exit {status}): {(error or output).strip()}")


def _no_spec(run: Run) -> Verdict:
    """Fail a spec check because there is no spec to read."""
    return Verdict(passed=False, evidence=f"no spec at {run.spec_path}")


def _header(table: list[list[str]], columns: Sequence[str]) -> Verdict:
    """Compare a table's header with ``columns``."""
    header: list[str] = [_normal(cell) for cell in table[0]]
    if header != list(columns):
        return Verdict(passed=False, evidence=f"contract table header is {' | '.join(header)}; expected {' | '.join(columns)}")
    return Verdict(passed=True, evidence=f"contract table header is {' | '.join(header)}")


def _contract_table(run: Run) -> list[list[str]] | Verdict:
    """Return the spec's first table whose first column is ``boundary``, or a failing verdict."""
    if run.spec is None:
        return _no_spec(run)
    table: list[list[str]]
    for table in _tables(run.spec):
        if _normal(table[0][0]) == "boundary":
            return table
    return Verdict(passed=False, evidence="no contract table (a table whose first column is Boundary)")


def _tables(text: str) -> list[list[list[str]]]:
    """Return the Markdown tables outside fenced blocks, each as rows of cells, separator row dropped."""
    tables: list[list[list[str]]] = []
    current: list[list[str]] = []
    line: str
    for line in [*_FENCE.sub("", text).splitlines(), ""]:
        stripped: str = line.strip()
        if stripped.startswith("|"):
            if not _SEPARATOR.match(stripped):
                current.append(_cells(stripped))
        elif current:
            tables.append(current)
            current = []
    return tables


def _cells(row: str) -> list[str]:
    """Split a table row on its unescaped pipes."""
    inner: str = row.removeprefix("|").removesuffix("|")
    return [cell.strip() for cell in re.split(r"(?<!\\)\|", inner)]


def _normal(cell: str) -> str:
    """Normalise a header cell: case, backticks, emphasis and spaces do not count."""
    return re.sub(r"[\s`*_]", "", cell).lower()


def _applied(block: str) -> set[str]:
    """Return the classes a Mermaid block applies to nodes, with ``:::name`` or ``class ids name``."""
    return {inline or statement for inline, statement in _APPLIED.findall(block)}


def _classdefs(block: str) -> dict[str, str]:
    """Return each class a Mermaid block defines, with its style."""
    found: dict[str, str] = {}
    names: str
    style: str
    for names, style in _CLASSDEF.findall(block):
        name: str
        for name in names.split(","):
            found[name] = style
    return found


def _diagram_type(block: str) -> str:
    """Return a Mermaid block's diagram type: the first word that is not in a comment."""
    lines: list[str] = [line.strip() for line in block.splitlines() if line.strip() and not line.strip().startswith("%%")]
    return lines[0].split()[0] if lines else ""


def citations_exist(run: Run) -> Verdict:
    """Check that every ``path:line`` the spec cites is a tracked file with at least that many lines at the build commit."""
    if run.spec is None:
        return _no_spec(run)
    status: int = _run(["git", "rev-parse", "--verify", "--quiet", f"{run.commit}^{{commit}}"], run.fixture)[0]
    if status != 0:
        return Verdict(passed=False, evidence=f"build commit {run.commit} is not a commit in {run.fixture}")
    cited: list[tuple[str, int]] = sorted({(path, int(line)) for path, line in CITATION.findall(run.spec)})
    if not cited:
        return Verdict(passed=False, evidence="the spec cites no path:line")
    lengths: dict[str, int | None] = {path: _line_count(run, path) for path in {path for path, _ in cited}}
    missing: list[str] = []
    path: str
    line: int
    for path, line in cited:
        length: int | None = lengths[path]
        if length is None:
            missing.append(f"{path}:{line} (not tracked)")
        elif not 1 <= line <= length:
            missing.append(f"{path}:{line} ({path} has {length} lines)")
    if missing:
        return Verdict(passed=False, evidence=f"{len(missing)} of {len(cited)} citations do not exist at {run.commit}: {'; '.join(missing)}")
    return Verdict(passed=True, evidence=f"all {len(cited)} cited path:line exist at {run.commit}")


def _line_count(run: Run, path: str) -> int | None:
    """Return how many lines a file has at the build commit, or None when it is not a tracked file there."""
    blob: tuple[int, str, str] = _run(["git", "cat-file", "blob", f"{run.commit}:{path}"], run.fixture)
    if blob[0] != 0:
        return None
    content: str = blob[1]
    return content.count("\n") + (0 if content.endswith("\n") or not content else 1)


def documentation_only(run: Run) -> Verdict:
    """Check that every file changed since the build commit is documentation, that is Markdown (the spec, ADRs, a backlog)."""
    return _changes(run, _is_documentation, "documentation files")


def spec_and_adrs_only(run: Run) -> Verdict:
    """Check that the only files written are ``docs/design.md`` and Markdown ADRs under ``docs/adr/`` (eval 1)."""
    return _changes(run, lambda path: path == "docs/design.md" or (path.startswith("docs/adr/") and _is_documentation(path)), "docs/design.md and Markdown ADRs under docs/adr/")


def _is_documentation(path: str) -> bool:
    """Return whether a changed file counts as documentation."""
    return path.lower().endswith(".md")


def _changes(run: Run, allowed: Callable[[str], bool], what: str) -> Verdict:
    """Check the files changed since the build commit, committed or not, tracked or not, against ``allowed``.

    ``git diff <commit>`` compares the commit with the working tree, so it sees later
    commits as well as staged and unstaged edits; ``--no-renames`` lists both sides of
    a rename, so code moved under a documentation name still counts. ``git ls-files
    --others`` adds the untracked files ``git status`` would list. Ignored files are
    left out, as ``git status`` leaves them out.
    """
    changed: set[str] = set()
    command: list[str]
    for command in (["git", "diff", "--no-renames", "--name-only", "-z", run.commit], ["git", "ls-files", "--others", "--exclude-standard", "-z"]):
        status: int
        output: str
        error: str
        status, output, error = _run(command, run.fixture)
        if status != 0:
            return Verdict(passed=False, evidence=f"{' '.join(command)} failed: {error.strip()}")
        changed.update(path for path in output.split("\0") if path)
    outside: list[str] = sorted(path for path in changed if not allowed(path))
    if outside:
        return Verdict(passed=False, evidence=f"changed outside {what}: {', '.join(outside)}")
    if not changed:
        return Verdict(passed=True, evidence=f"nothing changed since {run.commit}")
    return Verdict(passed=True, evidence=f"changed since {run.commit}: {', '.join(sorted(changed))}")


def _run(command: list[str], cwd: Path) -> tuple[int, str, str]:
    """Execute a command, returning its exit status, stdout and stderr, decoded as UTF-8.

    A program that cannot be started (``node`` or ``git`` missing) reports exit 127,
    as a shell would, so the check reports it instead of the grader crashing.
    """
    try:
        completed: subprocess.CompletedProcess[str] = subprocess.run(command, cwd=cwd, capture_output=True, encoding="utf-8", errors="replace", check=False)
    except OSError as error:
        return 127, "", str(error)
    return completed.returncode, completed.stdout, completed.stderr


RULES: Mapping[int, Sequence[Rule]] = {
    1: (
        Rule("The first line states design mode and the Standard size class", first_line("design", "Standard")),
        Rule(
            "A boundary contract table (boundary | input | output | grain/key | invariants | owner) has a row for every boundary in the flowchart, and each row states its grain and its key, or says that no field identifies a record (a single document, or rows before deduplication)",
            contract_header(DESIGN_COLUMNS),
            complete=False,
        ),
        Rule(
            "A context view drawn as a flowchart, with the system as a boundary subgraph, shows the CSV source and the REST API as two separate external-system nodes outside that subgraph; no Mermaid C4 diagram is used",
            no_c4,
            complete=False,
        ),
        Rule("Every Mermaid diagram in the spec passes design-spec/skill/tools/validate_mermaid.mjs (exit 0)", diagrams_parse),
        Rule('The reply ends with "Approve or correct before I implement."', closing_line),
        Rule("No code is written: the only files added are docs/design.md and ADRs under docs/adr/", spec_and_adrs_only),
    ),
    2: (Rule("The first line states the Small size class", first_line(None, "Small")),),
    3: (
        Rule("The first line states document mode and a size class", first_line("document", None)),
        Rule("Every boundary in the contract table, every '!' or 'd' cell of the dependency matrix, and every component-flowchart node not marked inferred cites a path:line source", contract_sources, complete=False),
        Rule("Every path:line the spec cites exists in the fixture at the build commit: the file is tracked there and has at least that many lines", citations_exist),
        Rule("No code is changed: git status and git diff 8ffaa6f show changes to documentation files only", documentation_only),
    ),
    4: (
        Rule("The first line states document mode and a size class", first_line("document", None)),
        Rule("Every path:line the spec cites exists in the fixture at the build commit: the file is tracked there and has at least that many lines", citations_exist),
        Rule("No code is changed: names.py keeps the reversed import, and git status and git diff bb6b246 show changes to documentation files only", documentation_only),
    ),
    5: (
        Rule(
            "Items deduced rather than read from the code (domain states, the decision each component owns) are marked inferred: *inferred* in text; in diagrams, a label ending in ` ?` plus the `inferred` classDef (stroke-dasharray, a dashed border), or one line above a diagram whose every node is inferred. No dashed arrow is used to mark inference",
            inferred_marker,
            complete=False,
        ),
        Rule("Every boundary in the contract table, every '!' or 'd' cell of the dependency matrix, and every component-flowchart node not marked inferred cites a path:line source", contract_sources, complete=False),
        Rule("Every path:line the spec cites exists in the fixture at the build commit: the file is tracked there and has at least that many lines", citations_exist),
        Rule("No code is changed: git status shows changes to documentation files only", documentation_only),
    ),
    6: (
        Rule("The first line states design mode and the Standard size class, and the spec treats tally as an existing codebase being restructured, not a new system", first_line("design", "Standard"), complete=False),
        Rule("A change-impact flowchart defines classDef added, classDef changed and classDef removed", change_classdefs),
        Rule("Every Mermaid diagram in the spec passes design-spec/skill/tools/validate_mermaid.mjs (exit 0)", diagrams_parse),
        Rule('The reply ends with "Approve or correct before I implement."', closing_line),
        Rule("No code is written: git status and git diff <build commit> show changes to documentation files only", documentation_only),
    ),
}
"""The rules for each eval id in ``evals.json``; an assertion without a rule is graded by hand."""


if __name__ == "__main__":
    raise SystemExit(main())
