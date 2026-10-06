"""Tests for the CI check that every changed module has a coverage record."""

from __future__ import annotations

import re
import runpy
import sys
from collections.abc import Sequence
from pathlib import Path

import pytest

from skill.tools.check_coverage_records import main
from skill.tools.hooks.stop_gate import Result

REPORT: str = '<coverage><packages><package><classes><class filename="calc/ops.py"/></classes></package></packages></coverage>'


class Git:
    """Answer exact git commands; any other command fails like git would."""

    def __init__(self, answers: dict[tuple[str, ...], Result]) -> None:
        """Initialize the fake.

        Args:
            answers: Result per exact argv.
        """
        self.answers: dict[tuple[str, ...], Result] = answers

    def __call__(self, command: Sequence[str]) -> Result:
        """Return the scripted answer, or a git-style failure for an unscripted command."""
        return self.answers.get(tuple(command), Result(128, f"fatal: unexpected {' '.join(command)}"))


def branch_changes(paths: Sequence[str]) -> Git:
    """Return a git fake whose branch, forked at abc123, changed these paths."""
    return Git(
        {
            ("git", "merge-base", "origin/main", "HEAD"): Result(0, "abc123\n"),
            ("git", "diff", "-z", "--name-only", "--relative", "--diff-filter=d", "abc123"): Result(0, "".join(f"{path}\0" for path in paths)),
        }
    )


def test_module_no_test_imports_fails(capsys: pytest.CaptureFixture[str]) -> None:
    """The case diff-cover misses: an untested module never reaches coverage.xml."""
    git: Git = branch_changes(["calc/extra.py", "calc/ops.py", "notes.ipynb", "README.md"])
    assert main(["--base", "origin/main"], git, lambda _: REPORT) == 1
    out: str = capsys.readouterr().out
    assert "calc/extra.py: no coverage record" in out
    assert "calc/ops.py" not in out
    assert "notes.ipynb" not in out


def test_adopting_the_standards_passes() -> None:
    """The adoption PR adds the vendored tools, which no project test imports."""
    vendored: list[str] = ["tools/__init__.py", "tools/changes.py", "tools/check_suppressions.py", "tools/hooks/guard_protected.py", "calc/ops.py"]
    assert main(["--base", "origin/main"], branch_changes(vendored), lambda _: REPORT) == 0


def test_every_changed_module_recorded_passes() -> None:
    assert main(["--base", "origin/main"], branch_changes(["calc/ops.py", "README.md"]), lambda _: REPORT) == 0


def test_reads_the_given_coverage_report() -> None:
    seen: list[Path] = []

    def read(path: Path) -> str:
        seen.append(path)
        return REPORT

    assert main(["--base", "origin/main", "--coverage", "build/coverage.xml"], branch_changes(["calc/ops.py"]), read) == 0
    assert seen == [Path("build/coverage.xml")]


def test_git_failure_fails_closed(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--base", "origin/main"], Git({}), lambda _: REPORT) == 1
    out: str = capsys.readouterr().out
    assert "`git merge-base origin/main HEAD` failed, so the change cannot be checked:" in out
    assert "fatal: unexpected git merge-base" in out


def test_reads_coverage_xml_by_default() -> None:
    seen: list[Path] = []

    def read(path: Path) -> str:
        seen.append(path)
        return REPORT

    assert main(["--base", "origin/main"], branch_changes(["calc/ops.py"]), read) == 0
    assert seen == [Path("coverage.xml")]


def test_base_is_required(capsys: pytest.CaptureFixture[str]) -> None:
    exit_info: pytest.ExceptionInfo[SystemExit]
    with pytest.raises(SystemExit) as exit_info:
        main([], Git({}), lambda _: REPORT)
    assert exit_info.value.code == 2
    assert "--base" in capsys.readouterr().err


def test_help_shows_the_module_docstring_and_option_help(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """The help is the tool's documentation: the docstring keeps its layout, and each option says what it takes."""
    monkeypatch.setenv("COLUMNS", "200")
    exit_info: pytest.ExceptionInfo[SystemExit]
    with pytest.raises(SystemExit) as exit_info:
        main(["--help"], Git({}), lambda _: REPORT)
    assert exit_info.value.code == 0
    out: str = capsys.readouterr().out
    assert "\n    uv run python -m tools.check_coverage_records --base origin/main\n" in out
    assert re.search(r"--base BASE +the branch's base ref, e\.g\. origin/main\n", out)
    assert re.search(r"--coverage COVERAGE +the Cobertura report pytest-cov wrote\n", out)


def test_runs_as_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run for real outside any repository: the merge base cannot be found, so the check fails."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    monkeypatch.setattr(sys, "argv", ["check_coverage_records", "--base", "origin/main"])
    # runpy re-executes the module; an already-imported copy would trigger a RuntimeWarning.
    monkeypatch.delitem(sys.modules, "skill.tools.check_coverage_records", raising=False)
    exit_info: pytest.ExceptionInfo[SystemExit]
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module("skill.tools.check_coverage_records", run_name="__main__")
    assert exit_info.value.code == 1
