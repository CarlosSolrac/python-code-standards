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

from skill.tools.hooks.stop_gate import AMBIGUOUS_RECORD, GitError, MissingRecords, Result, main, read_coverage_xml, run_command, unrecorded_modules

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
    """Return a minimal Cobertura report, as a bare ``--cov`` from the working directory writes it, recording these files."""
    classes: str = "".join(f'<class filename="{escape(path, {chr(34): "&quot;"})}"/>' for path in paths)
    return f"<coverage><sources><source>{escape(str(Path.cwd()))}</source></sources><packages><package><classes>{classes}</classes></package></packages></coverage>"


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


def per_source_report(sources: Sequence[str], filenames: Sequence[str]) -> str:
    """Return a Cobertura report as pytest-cov writes one for ``[tool.coverage.run] source``: names relative to their source."""
    roots: str = "".join(f"<source>{source}</source>" for source in sources)
    classes: str = "".join(f'<class filename="{name}"/>' for name in filenames)
    return f"<coverage><sources>{roots}</sources><packages><package><classes>{classes}</classes></package></packages></coverage>"


def test_a_name_is_recorded_relative_to_its_source(tmp_path: Path) -> None:
    """A workspace measuring several packages records ``ops.py``, not ``packages/calc/src/calc/ops.py``."""
    report: str = per_source_report([str(tmp_path / "packages/calc/src/calc"), str(tmp_path / "packages/fmt/src/fmt")], ["ops.py", "sub/deep.py"])
    assert unrecorded_modules(["packages/calc/src/calc/ops.py", "packages/fmt/src/fmt/sub/deep.py"], report, tmp_path) == MissingRecords([], [])


def test_a_file_outside_every_source_needs_no_record(tmp_path: Path) -> None:
    """Tests and deliberately unmeasured packages lie outside the configured sources, so coverage never records them."""
    report: str = per_source_report([str(tmp_path / "packages/calc/src/calc")], ["ops.py"])
    assert unrecorded_modules(["packages/calc/tests/test_ops.py", "tests/test_end_to_end.py", "packages/calc/src/calculator.py"], report, tmp_path) == MissingRecords([], [])


def test_a_module_inside_a_source_without_a_record_is_unrecorded(tmp_path: Path) -> None:
    report: str = per_source_report([str(tmp_path / "packages/calc/src/calc"), str(tmp_path / "packages/fmt/src/fmt")], ["ops.py"])
    assert unrecorded_modules(["packages/calc/src/calc/extra.py"], report, tmp_path) == MissingRecords(["packages/calc/src/calc/extra.py"], [])


def test_a_relative_source_resolves_against_the_project_root(tmp_path: Path) -> None:
    report: str = per_source_report(["."], ["calc/ops.py"])
    assert unrecorded_modules(["calc/ops.py", "calc/extra.py"], report, tmp_path) == MissingRecords(["calc/extra.py"], [])


def test_a_report_naming_no_source_measures_the_whole_project(tmp_path: Path) -> None:
    """No report, or one without ``<sources>``, must not wave every module through."""
    assert unrecorded_modules(["calc/ops.py"], "", tmp_path) == MissingRecords(["calc/ops.py"], [])


def two_packages(root: Path, files: Sequence[str]) -> str:
    """Create ``pkg_a`` and ``pkg_b`` holding these files; return a report measuring both, with one record per name, as Cobertura keeps."""
    name: str
    for name in files:
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).touch()
    return per_source_report([str(root / "pkg_a"), str(root / "pkg_b")], sorted({Path(name).relative_to(Path(name).parts[0]).as_posix() for name in files}))


def test_a_name_two_sources_share_cannot_be_attributed(tmp_path: Path) -> None:
    """Cobertura keeps one ``ops.py`` record for both packages (coveragepy#1508), so an unmeasured ``pkg_b/ops.py`` must not pass on ``pkg_a``'s record."""
    report: str = two_packages(tmp_path, ["pkg_a/ops.py", "pkg_b/ops.py"])
    assert unrecorded_modules(["pkg_a/ops.py", "pkg_b/ops.py"], report, tmp_path) == MissingRecords([], ["pkg_a/ops.py", "pkg_b/ops.py"])


def test_distinct_names_in_two_sources_are_attributed(tmp_path: Path) -> None:
    report: str = two_packages(tmp_path, ["pkg_a/ops.py", "pkg_b/fmt.py"])
    assert unrecorded_modules(["pkg_a/ops.py", "pkg_b/fmt.py"], report, tmp_path) == MissingRecords([], [])


def test_a_shared_name_with_no_record_is_untested(tmp_path: Path) -> None:
    report: str = per_source_report([str(tmp_path / "pkg_a"), str(tmp_path / "pkg_b")], [])
    (tmp_path / "pkg_a").mkdir()
    (tmp_path / "pkg_a/ops.py").touch()
    assert unrecorded_modules(["pkg_b/ops.py"], report, tmp_path) == MissingRecords(["pkg_b/ops.py"], [])


def test_a_shared_name_blocks_with_the_common_source_advice(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    report: str = two_packages(tmp_path, ["pkg_a/ops.py", "pkg_b/ops.py"])
    stdin: io.StringIO = io.StringIO(json.dumps({"hook_event_name": "Stop"}))
    stdout: io.StringIO = io.StringIO()
    assert main(stdin, stdout, FakeRunner(changed(modified=["pkg_b/ops.py", "pkg_b/new.py"])), lambda: report) == 0
    reason: str = str(json.loads(stdout.getvalue())["reason"])
    assert "No coverage record for:\n  pkg_b/new.py\nNo test imports these modules" in reason
    assert f"Coverage record cannot be attributed for:\n  pkg_b/ops.py\n{AMBIGUOUS_RECORD}" in reason


def test_a_shared_name_alone_reports_only_the_attribution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    report: str = two_packages(tmp_path, ["pkg_a/ops.py", "pkg_b/ops.py"])
    stdin: io.StringIO = io.StringIO(json.dumps({"hook_event_name": "Stop"}))
    stdout: io.StringIO = io.StringIO()
    assert main(stdin, stdout, FakeRunner(changed(modified=["pkg_b/ops.py"])), lambda: report) == 0
    reason: str = str(json.loads(stdout.getvalue())["reason"])
    assert "No coverage record" not in reason
    assert reason.endswith(f"\n\nCoverage record cannot be attributed for:\n  pkg_b/ops.py\n{AMBIGUOUS_RECORD}")


def test_the_ambiguity_advice_names_the_cause_and_the_fix() -> None:
    assert "Cobertura keeps one record per relative path" in AMBIGUOUS_RECORD
    assert "coveragepy/coveragepy#1508" in AMBIGUOUS_RECORD
    assert 'source = ["."]' in AMBIGUOUS_RECORD


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


def test_passing_gates_run_in_order_then_the_brief() -> None:
    """An empty brief adds nothing, so passing gates stay silent."""
    runner: FakeRunner = FakeRunner(changed(modified=["a.py"]))
    assert stop(runner) is None
    uv_calls: list[list[str]] = [call for call in runner.calls if call[0] == "uv"]
    assert [call[2] for call in uv_calls[:3]] == ["pre-commit", "pytest", "diff-cover"]
    assert uv_calls[3] == ["uv", "run", "--no-sync", "python", "-m", "tools.review_brief"]


def test_passing_gates_show_the_user_the_review_brief() -> None:
    brief: str = "# Review brief: changes since HEAD\n\n## Size: 1 files, +2 / -0\n"
    runner: FakeRunner = FakeRunner({**changed(modified=["a.py"]), "uv run --no-sync python -m tools.review_brief": Result(0, brief)})
    assert stop(runner) == {"systemMessage": brief.rstrip()}


def test_a_failing_brief_never_blocks_the_stop() -> None:
    runner: FakeRunner = FakeRunner({**changed(modified=["a.py"]), "uv run --no-sync python -m tools.review_brief": Result(1, "`git ...` failed")})
    assert stop(runner) is None


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


def spawn_failed(tool: str) -> Result:
    """Return what ``uv run`` prints for a tool the project environment does not install."""
    return Result(2, f"error: Failed to spawn: `{tool}`\n  Caused by: program not found")


@pytest.mark.parametrize("tool", ["pre-commit", "pytest", "diff-cover"])
def test_a_gate_tool_that_is_not_installed_is_named_as_a_setup_problem(tool: str) -> None:
    """No code change installs a tool; the agent is told to hand it to the user instead."""
    runner: FakeRunner = FakeRunner({**changed(modified=["a.py"]), f"uv run {tool}": spawn_failed(tool), f"uv run --no-sync {tool} --version": spawn_failed(tool)})
    output: dict[str, object] | None = stop(runner)
    assert output is not None
    reason: str = str(output["reason"])
    assert f"Quality gate failed: `{tool} (not installed)` (exit 2)." in reason
    assert reason.endswith(
        f"program not found\n\n`{tool}` is not installed in the project environment, so this gate cannot run. Change no code: tell the user to add it with `uv add --dev {tool}`, or to re-run setup-standards.sh with -y --update."
    )


@pytest.mark.parametrize("probe_exit", [1, 127])
def test_a_missing_tool_is_named_whatever_nonzero_exit_the_probe_reports(probe_exit: int) -> None:
    """Only a successful probe clears the tool; any other exit with the spawn failure message means it is not installed."""
    probe: Result = Result(probe_exit, spawn_failed("pytest").output)
    runner: FakeRunner = FakeRunner({**changed(modified=["a.py"]), "uv run pytest": spawn_failed("pytest"), "uv run --no-sync pytest --version": probe})
    output: dict[str, object] | None = stop(runner)
    assert output is not None
    assert "`pytest (not installed)`" in str(output["reason"])


def test_a_failing_gate_tool_that_is_installed_keeps_its_command() -> None:
    runner: FakeRunner = FakeRunner({**changed(modified=["a.py"]), "uv run pytest": Result(1, "1 failed")})
    output: dict[str, object] | None = stop(runner)
    assert output is not None
    assert "not installed" not in str(output["reason"])
    assert runner.ran("uv run --no-sync pytest --version")


def test_a_uv_failure_is_not_mistaken_for_a_missing_tool() -> None:
    """A malformed pyproject.toml fails the probe too, though the tool is installed; its diagnostic must survive."""
    broken: Result = Result(2, "error: Failed to parse: `pyproject.toml`\n  Caused by: TOML parse error at line 161, column 9")
    runner: FakeRunner = FakeRunner({**changed(modified=["a.py"]), "uv run pre-commit": broken, "uv run --no-sync pre-commit --version": broken})
    output: dict[str, object] | None = stop(runner)
    assert output is not None
    reason: str = str(output["reason"])
    assert "Quality gate failed: `uv run pre-commit run --files a.py` (exit 2)." in reason
    assert "not installed" not in reason


def test_a_missing_tool_after_a_retry_is_named_to_the_user() -> None:
    runner: FakeRunner = FakeRunner({**changed(modified=["a.py"]), "uv run pre-commit": spawn_failed("pre-commit"), "uv run --no-sync pre-commit --version": spawn_failed("pre-commit")})
    output: dict[str, object] | None = stop(runner, active=True)
    assert output == {"systemMessage": "GATE FAILED: `pre-commit (not installed)` still fails after a retry. Claude stopped anyway; this work is NOT verified."}


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
