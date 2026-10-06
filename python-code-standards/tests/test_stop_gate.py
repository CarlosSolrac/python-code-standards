"""Tests for the Stop hook that keeps the agent working until the gates pass.

Every subprocess goes through an injected runner, so these tests never run git,
pre-commit, or pytest for real.
"""

from __future__ import annotations

import io
import json
import runpy
import sys
from collections.abc import Sequence
from pathlib import Path
from xml.sax.saxutils import escape

import pytest

from skill.tools.hooks.stop_gate import GitError, Result, main, read_coverage_xml, run_command

STOP_GATE: Path = Path(__file__).resolve().parent.parent / "skill" / "tools" / "hooks" / "stop_gate.py"
PASS: Result = Result(returncode=0, output="")


class FakeRunner:
    """Answer each command by its leading words and record every call."""

    def __init__(self, answers: dict[str, Result]) -> None:
        """Initialize the runner.

        Args:
            answers: Result per space-joined command prefix; unmatched commands pass.
        """
        self.answers: dict[str, Result] = answers
        self.calls: list[list[str]] = []

    def __call__(self, command: Sequence[str]) -> Result:
        """Record the command and return the answer for its longest matching prefix."""
        self.calls.append(list(command))
        joined: str = " ".join(command)
        matches: list[str] = [prefix for prefix in self.answers if joined.startswith(prefix)]
        if not matches:
            return PASS
        return self.answers[max(matches, key=len)]

    def ran(self, prefix: str) -> bool:
        """Return whether any recorded command starts with the prefix."""
        return any(" ".join(call).startswith(prefix) for call in self.calls)


def nul_listing(paths: Sequence[str]) -> Result:
    """Return a git listing as ``-z`` prints it: each path verbatim, NUL-terminated."""
    return Result(0, "".join(f"{path}\0" for path in paths))


def changed(modified: Sequence[str] = (), cached: Sequence[str] = (), deleted: Sequence[str] = (), cached_deleted: Sequence[str] = ()) -> dict[str, Result]:
    """Return git answers describing the working tree.

    Args:
        modified: Unstaged and untracked paths, including unstaged deletions, as ``ls-files -m -o`` lists them.
        cached: Staged paths that still exist.
        deleted: Unstaged deletions.
        cached_deleted: Staged deletions.
    """
    return {
        "git ls-files -z --modified --others": nul_listing(modified),
        "git diff -z --cached --name-only --relative --diff-filter=d": nul_listing(cached),
        "git ls-files -z --deleted": nul_listing(deleted),
        "git diff -z --cached --name-only --relative --diff-filter=D": nul_listing(cached_deleted),
    }


def coverage_xml(paths: Sequence[str]) -> str:
    """Return a minimal Cobertura report, as pytest-cov writes it, recording these files."""
    classes: str = "".join(f'<class filename="{escape(path, {chr(34): "&quot;"})}"/>' for path in paths)
    return f"<coverage><sources><source>/repo</source></sources><packages><package><classes>{classes}</classes></package></packages></coverage>"


def stop(runner: FakeRunner, *, active: bool = False, covered: Sequence[str] = ("a.py", "b.py")) -> dict[str, object] | None:
    """Run the hook on one Stop event; return its parsed output, or None when silent.

    Args:
        runner: Answers every command the hook runs.
        active: Whether this stop is already a retry.
        covered: Files the coverage report records.
    """
    stdin: io.StringIO = io.StringIO(json.dumps({"hook_event_name": "Stop", "stop_hook_active": active}))
    stdout: io.StringIO = io.StringIO()
    report: str = coverage_xml(covered)
    assert main(stdin, stdout, runner, lambda: report) == 0
    if not stdout.getvalue():
        return None
    output: dict[str, object] = json.loads(stdout.getvalue())
    return output


def test_no_changed_python_skips_every_gate() -> None:
    runner: FakeRunner = FakeRunner(changed(modified=["README.md"]))
    assert stop(runner) is None
    assert not runner.ran("uv")


def test_git_failure_blocks_with_its_diagnostics() -> None:
    """A git error is not "nothing changed": skipping the gates silently would pass unverified work."""
    runner: FakeRunner = FakeRunner({"git": Result(128, "fatal: detected dubious ownership in repository at '/repo'")})
    output: dict[str, object] | None = stop(runner)
    assert output is not None
    assert output["decision"] == "block"
    reason: str = str(output["reason"])
    assert "git ls-files" in reason
    assert "dubious ownership" in reason
    assert not runner.ran("uv")


def test_changed_module_without_a_coverage_record_blocks() -> None:
    """A module no test imports never reaches coverage.xml, and diff-cover silently skips it."""
    runner: FakeRunner = FakeRunner(changed(modified=["calc/extra.py", "calc/ops.py", "notes.ipynb"]))
    output: dict[str, object] | None = stop(runner, covered=["calc/ops.py"])
    assert output is not None
    reason: str = str(output["reason"])
    assert "calc/extra.py" in reason
    assert "calc/ops.py" not in reason
    assert "notes.ipynb" not in reason
    assert not runner.ran("uv run diff-cover")


def test_vendored_tooling_needs_no_coverage_record() -> None:
    """Setup vendors the gate tools, tested upstream; a project's own tools stay gated."""
    runner: FakeRunner = FakeRunner(changed(modified=["tools/check_declarations.py", "tools/hooks/stop_gate.py", "tools/report.py"]))
    output: dict[str, object] | None = stop(runner, covered=[])
    assert output is not None
    reason: str = str(output["reason"])
    assert "tools/report.py" in reason
    assert "check_declarations" not in reason
    assert "tools/hooks/stop_gate.py" not in reason


def test_coverage_record_matches_escaped_file_names() -> None:
    names: list[str] = ['a&b "q".py']
    runner: FakeRunner = FakeRunner(changed(modified=names))
    assert stop(runner, covered=names) is None


def test_read_coverage_xml(tmp_path: Path) -> None:
    report: Path = tmp_path / "coverage.xml"
    assert read_coverage_xml(report) == ""
    report.write_text("<coverage/>", encoding="utf-8")
    assert read_coverage_xml(report) == "<coverage/>"


def test_changed_files_combine_staged_and_unstaged_without_deleted() -> None:
    runner: FakeRunner = FakeRunner(changed(modified=["b.py", "notes.ipynb", "gone.py", "README.md"], cached=["a.py", "b.py"], deleted=["gone.py"]))
    assert stop(runner) is None
    assert ["uv", "run", "pre-commit", "run", "--files", "a.py", "b.py", "notes.ipynb"] in runner.calls


@pytest.mark.parametrize(
    "deletion",
    [{"modified": ["calc/ops.py"], "deleted": ["calc/ops.py"]}, {"cached_deleted": ["calc/ops.py"]}],
    ids=["unstaged", "staged"],
)
def test_deleted_python_alone_still_runs_tests_but_not_pre_commit(deletion: dict[str, list[str]]) -> None:
    """Deleting a module can break its importers, so tests run; the gone file is not linted."""
    runner: FakeRunner = FakeRunner({**changed(**deletion), "uv run pytest": Result(1, "ModuleNotFoundError: No module named 'calc.ops'")})
    output: dict[str, object] | None = stop(runner)
    assert output is not None
    assert "ModuleNotFoundError" in str(output["reason"])
    assert not runner.ran("uv run pre-commit")


def test_deleted_python_with_edits_lints_only_the_existing_files() -> None:
    runner: FakeRunner = FakeRunner(changed(modified=["a.py"], cached_deleted=["gone.py"]))
    assert stop(runner) is None
    assert ["uv", "run", "pre-commit", "run", "--files", "a.py"] in runner.calls
    assert runner.ran("uv run pytest")


def test_paths_git_would_quote_are_still_gated() -> None:
    """Non-ASCII, spaced, and newline names reach the gates verbatim, not in git's quoted form."""
    names: list[str] = ["tests/test_café.py", "src/my module.py", "odd\nname.py"]
    runner: FakeRunner = FakeRunner(changed(modified=names))
    assert stop(runner, covered=names) is None
    assert ["uv", "run", "pre-commit", "run", "--files", *sorted(names)] in runner.calls
    git_calls: list[list[str]] = [call for call in runner.calls if call[0] == "git"]
    assert git_calls
    assert all("-z" in call for call in git_calls)


def test_passing_gates_stay_silent_and_run_in_order() -> None:
    runner: FakeRunner = FakeRunner(changed(modified=["a.py"]))
    assert stop(runner) is None
    gates: list[str] = [call[2] for call in runner.calls if call[0] == "uv"]
    assert gates == ["pre-commit", "pytest", "diff-cover"]


def test_failing_gate_blocks_the_stop_with_its_output() -> None:
    runner: FakeRunner = FakeRunner({**changed(modified=["a.py"]), "uv run pre-commit": Result(1, "a.py:3:1: F401 unused import")})
    output: dict[str, object] | None = stop(runner)
    assert output is not None
    assert output["decision"] == "block"
    reason: str = str(output["reason"])
    assert "uv run pre-commit run --files a.py" in reason
    assert "F401 unused import" in reason
    assert not runner.ran("uv run pytest")


def test_later_gate_failure_is_reported() -> None:
    runner: FakeRunner = FakeRunner({**changed(modified=["a.py"]), "uv run diff-cover": Result(1, "a.py (50.0%): Missing lines 4")})
    output: dict[str, object] | None = stop(runner)
    assert output is not None
    assert "Quality gate failed: `uv run diff-cover coverage.xml --compare-branch=main --include-untracked --fail-under=100` (exit 1)." in str(output["reason"])


def test_test_failure_names_the_exact_command() -> None:
    runner: FakeRunner = FakeRunner({**changed(modified=["a.py"]), "uv run pytest": Result(1, "1 failed")})
    output: dict[str, object] | None = stop(runner)
    assert output is not None
    assert "Quality gate failed: `uv run pytest -q --cov --cov-branch --cov-report=xml` (exit 1)." in str(output["reason"])


def test_coverage_record_failure_lists_each_module_on_its_own_line() -> None:
    runner: FakeRunner = FakeRunner(changed(modified=["calc/a.py", "calc/b.py"]))
    output: dict[str, object] | None = stop(runner, covered=[])
    assert output is not None
    reason: str = str(output["reason"])
    assert "Quality gate failed: `coverage record check` (exit 1)." in reason
    assert "No coverage record for:\n  calc/a.py\n  calc/b.py\nNo test imports these modules" in reason


def test_git_listings_use_the_exact_commands() -> None:
    """Every flag matters: without --exclude-standard, ignored files (.venv, build output) would be gated."""
    runner: FakeRunner = FakeRunner(changed(modified=["README.md"]))
    stop(runner)
    assert runner.calls == [
        ["git", "ls-files", "-z", "--modified", "--others", "--exclude-standard"],
        ["git", "diff", "-z", "--cached", "--name-only", "--relative", "--diff-filter=d"],
        ["git", "ls-files", "-z", "--deleted"],
        ["git", "diff", "-z", "--cached", "--name-only", "--relative", "--diff-filter=D"],
    ]


def test_git_error_message_is_the_command() -> None:
    assert str(GitError(["git", "ls-files", "-z"], Result(128, "fatal"))) == "git ls-files -z"


def test_long_output_keeps_only_the_tail() -> None:
    noise: str = "x" * 20_000
    runner: FakeRunner = FakeRunner({**changed(modified=["a.py"]), "uv run pytest": Result(1, noise + "FAILED tests/test_a.py::test_one")})
    output: dict[str, object] | None = stop(runner)
    assert output is not None
    reason: str = str(output["reason"])
    assert "FAILED tests/test_a.py::test_one" in reason
    assert len(reason) < 10_000


def test_failure_after_a_retry_lets_the_stop_through_and_warns_the_user() -> None:
    runner: FakeRunner = FakeRunner({**changed(modified=["a.py"]), "uv run pytest": Result(1, "1 failed")})
    output: dict[str, object] | None = stop(runner, active=True)
    assert output is not None
    assert "decision" not in output
    assert "GATE FAILED" in str(output["systemMessage"])


def test_run_command_returns_status_and_combined_output() -> None:
    result: Result = run_command([sys.executable, "-c", "import sys; print('out'); print('err', file=sys.stderr); sys.exit(3)"])
    assert result.returncode == 3
    assert "out" in result.output
    assert "err" in result.output


def test_run_command_decodes_output_as_utf8() -> None:
    """Git prints paths as UTF-8 bytes; a locale decode (cp1252 on Windows) would garble them."""
    result: Result = run_command([sys.executable, "-c", "import sys; sys.stdout.buffer.write('tests/test_café.py'.encode('utf-8'))"])
    assert result.output == "tests/test_café.py"


def test_run_command_replaces_undecodable_bytes() -> None:
    """A tool printing invalid UTF-8 must not crash the gate; the bad byte becomes U+FFFD."""
    result: Result = run_command([sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'ok \\xff end')"])
    assert result.output == "ok � end"


def test_runs_as_script(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """Run for real outside a git repository, git fails, so the script blocks and exits 0."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"stop_hook_active": False})))
    exit_info: pytest.ExceptionInfo[SystemExit]
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_path(str(STOP_GATE), run_name="__main__")
    assert exit_info.value.code == 0
    output: dict[str, object] = json.loads(capsys.readouterr().out)
    assert output["decision"] == "block"
    assert "not a git repository" in str(output["reason"])
