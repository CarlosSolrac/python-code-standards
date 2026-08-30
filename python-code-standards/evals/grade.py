"""Score generated Python against the standards, mechanically.

Given a directory of files produced by one eval run, this reports violation
counts from the declaration checker, Ruff, and Pyright. It makes no judgment
calls: every number here comes from a tool, so the same output scores the same
way regardless of who ran it.

Whether the agent used uv, claimed an unrun check passed, or kept its diff scoped
is not measurable here — those live in the transcript. Read them there.

Compare a with-skill run against a without-skill baseline on identical prompts.
A single run's absolute numbers mean little; the difference between the two is
the measurement.

Usage:
    uv run python -m evals.grade runs/with-skill --json scores.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Score:
    """Mechanical results for one eval run."""

    run: str
    files: int
    lines: int
    declaration_violations: int
    ruff_violations: int
    ruff_by_rule: dict[str, int]
    pyright_errors: int
    notes: list[str]


def _run(command: list[str], cwd: Path) -> tuple[int, str]:
    """Execute a command, returning its exit status and combined output."""
    completed: subprocess.CompletedProcess[str] = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    return completed.returncode, completed.stdout + completed.stderr


def count_declarations(target: Path, checker: Path) -> int:
    """Return the number of declaration-rule violations under a directory."""
    status: int
    output: str
    status, output = _run([sys.executable, str(checker), str(target)], target.parent)
    if status not in (0, 1):
        return -1
    return sum(1 for line in output.splitlines() if "bound before annotation" in line)


def count_ruff(target: Path, config: Path) -> tuple[int, dict[str, int]]:
    """Return the total Ruff violations and a per-rule breakdown.

    The config is copied into the run directory and Ruff is invoked from there,
    because per-file ignores such as ``tests/**/*.py`` resolve relative to the
    config's own location. Pointing at a config elsewhere silently fails to match
    them, which penalises a run for exactly the findings the standards waive.
    """
    local: Path = target / "pyproject.toml"
    if not local.exists():
        local.write_text(config.read_text(encoding="utf-8"), encoding="utf-8")

    status: int
    output: str
    status, output = _run(
        ["uvx", "ruff@latest", "check", "--no-cache", "--output-format", "json", "."],
        target,
    )
    if status not in (0, 1):
        return -1, {}

    # uvx prints installer chatter before the JSON payload.
    start: int = output.find("[")
    if start == -1:
        return -1, {}
    try:
        findings: list[dict[str, object]] = json.loads(output[start:])
    except json.JSONDecodeError:
        return -1, {}
    by_rule: dict[str, int] = {}
    finding: dict[str, object]
    for finding in findings:
        code: str = str(finding.get("code") or "?")
        by_rule[code] = by_rule.get(code, 0) + 1
    return len(findings), dict(sorted(by_rule.items()))


def count_pyright(target: Path, config: Path) -> int:
    """Return the number of Pyright errors, or -1 when Pyright could not run."""
    status: int
    output: str
    status, output = _run(["uvx", "pyright@latest", "--project", str(config), "--outputjson", str(target)], target.parent)
    if status not in (0, 1):
        return -1
    try:
        report: dict[str, object] = json.loads(output[output.index("{") :])
    except (ValueError, json.JSONDecodeError):
        return -1
    summary: object = report.get("summary", {})
    if isinstance(summary, dict):
        return int(summary.get("errorCount", -1))
    return -1


def grade(run: Path, checker: Path, config: Path) -> Score:
    """Score one run directory.

    Args:
        run: Directory holding the files an agent produced.
        checker: Path to ``check_declarations.py``.
        config: Path to the ``pyproject.toml`` carrying the standards.

    Returns:
        Mechanical counts for the run.
    """
    sources: list[Path] = sorted(run.rglob("*.py"))
    lines: int = sum(len(path.read_text(encoding="utf-8").splitlines()) for path in sources)
    text: str = "\n".join(path.read_text(encoding="utf-8") for path in sources)

    ruff_total: int
    ruff_rules: dict[str, int]
    ruff_total, ruff_rules = count_ruff(run, config)

    notes: list[str] = []
    if not sources:
        notes.append("no Python files found; check the run directory")
    if "pip install" in text or "python -m venv" in text:
        notes.append("mentions pip or venv; the standards require uv")
    if any("pyright" in note for note in notes):
        notes.append("pyright needs the run's own dependencies installed to be meaningful")

    return Score(
        run=run.name,
        files=len(sources),
        lines=lines,
        declaration_violations=count_declarations(run, checker),
        ruff_violations=ruff_total,
        ruff_by_rule=ruff_rules,
        pyright_errors=count_pyright(run, config),
        notes=notes,
    )


def main(argv: list[str] | None = None) -> int:
    """Grade one or more run directories and print a comparison.

    Args:
        argv: Command-line arguments, defaulting to ``sys.argv[1:]``.

    Returns:
        0 always; this reports, it does not gate.
    """
    parser: argparse.ArgumentParser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", nargs="+", type=Path)
    parser.add_argument("--checker", type=Path, default=Path("skill/tools/check_declarations.py"))
    parser.add_argument("--config", type=Path, default=Path("pyproject.toml"))
    parser.add_argument("--json", type=Path, default=None)
    args: argparse.Namespace = parser.parse_args(argv)

    scores: list[Score] = []
    run: Path
    for run in args.runs:
        # Resolve every path: the tools below run with a different working
        # directory, so a relative run path would resolve twice and match nothing.
        scores.append(grade(run.resolve(), args.checker.resolve(), args.config.resolve()))

    print(f"{'run':<24}{'files':>6}{'lines':>7}{'decl':>7}{'ruff':>7}{'pyright':>9}")
    score: Score
    for score in scores:
        print(f"{score.run:<24}{score.files:>6}{score.lines:>7}{score.declaration_violations:>7}{score.ruff_violations:>7}{score.pyright_errors:>9}")
        note: str
        for note in score.notes:
            print(f"  ! {note}")

    if args.json is not None:
        args.json.write_text(json.dumps([asdict(score) for score in scores], indent=2), encoding="utf-8")
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
