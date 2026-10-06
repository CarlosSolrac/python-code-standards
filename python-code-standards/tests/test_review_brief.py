"""Tests for the review brief: one screen that says where a reviewer should look."""

from __future__ import annotations

import json
import re
import runpy
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from skill.tools.hooks.stop_gate import GitError, Result
from skill.tools.review_brief import build_brief, main, read_text

HEAD: tuple[str, ...] = ("git", "rev-parse", "--verify", "--quiet", "HEAD")
NUMSTAT: tuple[str, ...] = ("git", "diff", "-z", "--numstat", "--no-renames", "--relative", "HEAD")
UNTRACKED: tuple[str, ...] = ("git", "ls-files", "-z", "--others", "--exclude-standard")
BASE_PYPROJECT: tuple[str, ...] = ("git", "show", "HEAD:./pyproject.toml")
NOQA: str = "# " + "noqa"  # split so this file holds no suppression of its own


class Git:
    """Answer exact commands; anything unscripted fails like git would."""

    def __init__(self, answers: dict[tuple[str, ...], Result]) -> None:
        """Initialize the fake.

        Args:
            answers: Result per exact argv.
        """
        self.answers: dict[tuple[str, ...], Result] = answers
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, command: Sequence[str]) -> Result:
        """Record the command and return its scripted answer."""
        self.calls.append(tuple(command))
        return self.answers.get(tuple(command), Result(128, f"fatal: unexpected {' '.join(command)}"))


def complexity_command(files: Sequence[str]) -> tuple[str, ...]:
    """Return the complexipy invocation the brief makes for these files."""
    # --ignore-complexity: an over-cap function must still be reported, not read as a failed run.
    return ("uv", "run", "--no-sync", "complexipy", "--ignore-complexity", "--output-format", "json", "--output", ".complexipy_cache/review-brief.json", *files)


def working_tree(numstat: str, untracked: str = "", extra: dict[tuple[str, ...], Result] | None = None) -> Git:
    """Return a git fake for a working tree with HEAD and these changes."""
    answers: dict[tuple[str, ...], Result] = {HEAD: Result(0, "abc\n"), NUMSTAT: Result(0, numstat), UNTRACKED: Result(0, untracked)}
    answers.update(extra or {})
    return Git(answers)


def files_reader(files: dict[str, str]) -> Callable[[str], str]:
    """Return a reader over an in-memory file map; a missing file raises like the real one."""

    def read(path: str) -> str:
        if path not in files:
            raise FileNotFoundError(path)
        return files[path]

    return read


def brief(git: Git, files: dict[str, str], base: str | None = None) -> str:
    """Build the brief over in-memory files."""
    return build_brief(base, git, files_reader(files))


def test_empty_change_says_there_is_nothing_to_review() -> None:
    assert brief(working_tree(""), {}) == "Review brief: no changes since HEAD."


def test_size_lists_each_file_with_lines_added_and_removed() -> None:
    git: Git = working_tree("3\t1\tREADME.md\x00-\t-\tlogo.png\x00", untracked="notes.txt\x00")
    text: str = brief(git, {"notes.txt": "a\nb\n"})
    assert "## Size: 3 files, +5 / -1" in text
    assert "- `README.md` +3 / -1" in text
    assert "- `logo.png` binary" in text
    assert "- `notes.txt` +2 / -0 (new, untracked)" in text


def test_gate_files_are_called_out() -> None:
    git: Git = working_tree("1\t0\tREADME.md\x001\t0\tpyproject.toml\x00", extra={BASE_PYPROJECT: Result(0, "")})
    text: str = brief(git, {"pyproject.toml": "", "README.md": "x\n"})
    assert "## Gate files touched: 1\n- `pyproject.toml`" in text


def test_dependency_changes_are_listed() -> None:
    before: str = '[project]\ndependencies = ["requests>=2"]\n[dependency-groups]\ndev = ["pytest>=9"]\n'
    after: str = '[project]\ndependencies = ["httpx>=0.27"]\n[dependency-groups]\ndev = ["pytest>=9", "hypothesis>=6"]\n'
    git: Git = working_tree("1\t1\tpyproject.toml\x00", extra={BASE_PYPROJECT: Result(0, before)})
    text: str = brief(git, {"pyproject.toml": after})
    assert "## Dependencies: +2 / -1\n- added `httpx>=0.27`\n- added `hypothesis>=6`\n- removed `requests>=2`" in text


def test_suppressions_split_approved_from_unapproved() -> None:
    diff: str = f"@@ -0,0 +1,2 @@\n+run(x)  {NOQA}: S603\n+import os  {NOQA}: F401\n"
    git: Git = working_tree(
        "2\t0\ttools/hooks/stop_gate.py\x00",
        extra={
            ("git", "ls-files", "-z", "--others", "--exclude-standard", "--", "tools/hooks/stop_gate.py"): Result(0, ""),
            ("git", "diff", "-U0", "--no-color", "--no-ext-diff", "HEAD", "--", "tools/hooks/stop_gate.py"): Result(0, diff),
            complexity_command(["tools/hooks/stop_gate.py"]): Result(0, ""),
        },
    )
    allow: str = '[[suppression]]\npath = "tools/hooks/stop_gate.py"\ncode = "S603"\nreason = "fixed argv"\n'
    files: dict[str, str] = {
        "tools/hooks/stop_gate.py": f"run(x)  {NOQA}: S603\nimport os  {NOQA}: F401\n",
        "suppressions.toml": allow,
        ".complexipy_cache/review-brief.json": "[]",
    }
    text: str = brief(git, files)
    assert "## Suppressions added: 2 (1 unapproved)\n- `tools/hooks/stop_gate.py:2` `noqa: F401` UNAPPROVED\n- `tools/hooks/stop_gate.py:1` `noqa: S603` approved" in text


def test_complexity_shows_the_highest_changed_functions_first() -> None:
    report: list[dict[str, object]] = [{"path": "src/app.py", "function_name": name, "complexity": score} for name, score in [("a", 2), ("b", 14), ("c", 9), ("d", 0), ("e", 5), ("f", 11)]]
    git: Git = working_tree(
        "1\t0\tsrc/app.py\x00",
        extra={
            ("git", "ls-files", "-z", "--others", "--exclude-standard", "--", "src/app.py"): Result(0, ""),
            ("git", "diff", "-U0", "--no-color", "--no-ext-diff", "HEAD", "--", "src/app.py"): Result(0, ""),
            complexity_command(["src/app.py"]): Result(0, ""),
        },
    )
    text: str = brief(git, {"src/app.py": "", ".complexipy_cache/review-brief.json": json.dumps(report)})
    assert "## Complexity: highest in changed files (cap 15)\n- `src/app.py` `b` 14\n- `src/app.py` `f` 11\n- `src/app.py` `c` 9\n- `src/app.py` `e` 5\n- `src/app.py` `a` 2\n" in text


def test_coverage_and_mutation_sections_read_their_reports() -> None:
    git: Git = working_tree(
        "1\t0\tsrc/app.py\x001\t0\tsrc/util.py\x00",
        extra={
            ("git", "ls-files", "-z", "--others", "--exclude-standard", "--", "src/app.py"): Result(0, ""),
            ("git", "ls-files", "-z", "--others", "--exclude-standard", "--", "src/util.py"): Result(0, ""),
            ("git", "diff", "-U0", "--no-color", "--no-ext-diff", "HEAD", "--", "src/app.py"): Result(0, ""),
            ("git", "diff", "-U0", "--no-color", "--no-ext-diff", "HEAD", "--", "src/util.py"): Result(0, ""),
            complexity_command(["src/app.py", "src/util.py"]): Result(1, "complexipy: not installed"),
        },
    )
    files: dict[str, str] = {
        "src/app.py": "",
        "src/util.py": "",
        "coverage.xml": '<coverage><class filename="src/app.py"/></coverage>',
        "mutants/survivors.txt": "    src.app.x_f__mutmut_1: survived\n    src.app.x_f__mutmut_2: survived\n    other.x_g__mutmut_1: survived\n",
    }
    text: str = brief(git, files)
    assert "## Complexity: not measured (complexipy did not run)" in text
    assert "## Coverage: 1 changed module without a coverage record\n- `src/util.py`" in text
    assert "## Mutation: 2 survivors in changed modules (from the last mutation run)\n- `src/app.py` 2" in text


def test_missing_reports_are_named() -> None:
    git: Git = working_tree(
        "1\t0\tsrc/app.py\x00",
        extra={
            ("git", "ls-files", "-z", "--others", "--exclude-standard", "--", "src/app.py"): Result(0, ""),
            ("git", "diff", "-U0", "--no-color", "--no-ext-diff", "HEAD", "--", "src/app.py"): Result(0, ""),
            complexity_command(["src/app.py"]): Result(0, ""),
        },
    )
    text: str = brief(git, {"src/app.py": "", ".complexipy_cache/review-brief.json": "[]"})
    assert "## Coverage: no coverage.xml (run the tests with --cov)" in text
    assert "## Mutation: no mutants/survivors.txt (run bash tools/mutation.sh)" in text
    assert "## Suppressions added: none" in text
    assert "## Dependencies: no change" in text
    assert "## Gate files touched: none" in text


def test_base_mode_compares_against_the_merge_base() -> None:
    git: Git = Git(
        {
            ("git", "merge-base", "origin/main", "HEAD"): Result(0, "abc123\n"),
            ("git", "diff", "-z", "--numstat", "--no-renames", "--relative", "abc123"): Result(0, "1\t0\tREADME.md\x00"),
            UNTRACKED: Result(0, ""),
        }
    )
    assert brief(git, {}, base="origin/main").startswith("# Review brief: changes since origin/main\n")


def test_main_prints_the_brief(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([], working_tree(""), files_reader({})) == 0
    assert capsys.readouterr().out == "Review brief: no changes since HEAD.\n"


def test_main_reports_git_failure(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--base", "origin/missing"], Git({}), files_reader({})) == 1
    assert "`git merge-base origin/missing HEAD` failed" in capsys.readouterr().out


def test_read_text_replaces_undecodable_bytes(tmp_path: Path) -> None:
    path: Path = tmp_path / "f.bin"
    path.write_bytes(b"ok \xff")
    assert read_text(str(path)) == "ok �"


def test_runs_as_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Outside a repository git fails, so the brief reports it and exits 1."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    monkeypatch.setattr(sys, "argv", ["review_brief", "--base", "origin/main"])
    monkeypatch.delitem(sys.modules, "skill.tools.review_brief", raising=False)
    exit_info: pytest.ExceptionInfo[SystemExit]
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module("skill.tools.review_brief", run_name="__main__")
    assert exit_info.value.code == 1


def python_change(path: str) -> dict[tuple[str, ...], Result]:
    """Return git answers for a tracked Python file whose diff adds nothing."""
    return {
        ("git", "ls-files", "-z", "--others", "--exclude-standard", "--", path): Result(0, ""),
        ("git", "diff", "-U0", "--no-color", "--no-ext-diff", "HEAD", "--", path): Result(0, ""),
    }


def test_before_the_first_commit_every_file_is_new() -> None:
    git: Git = Git(
        {
            HEAD: Result(1, ""),
            ("git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"): Result(0, "README.md\x00"),
        }
    )
    text: str = brief(git, {"README.md": "a\nb\nc\n"})
    assert "- `README.md` +3 / -0 (new, untracked)" in text


def test_git_failure_in_the_size_listing_raises() -> None:
    with pytest.raises(GitError):
        brief(Git({HEAD: Result(0, "abc\n")}), {})


def test_deleted_files_are_sized_but_not_analysed() -> None:
    git: Git = working_tree("0\t4\tgone.py\x000\t2\tpyproject.toml\x00", extra={BASE_PYPROJECT: Result(0, '[project]\ndependencies = ["requests>=2"]\n')})
    text: str = brief(git, {})
    assert "- `gone.py` +0 / -4" in text
    assert "## Dependencies: +0 / -1\n- removed `requests>=2`" in text
    assert "## Complexity: no changed Python modules" in text


def test_non_list_dependency_groups_are_ignored() -> None:
    after: str = '[dependency-groups]\ndev = ["ruff>=0.14", {include-group = "lint"}]\nlint = "not-a-list"\n'
    git: Git = working_tree("1\t0\tpyproject.toml\x00", extra={BASE_PYPROJECT: Result(0, "")})
    assert "## Dependencies: +1 / -0\n- added `ruff>=0.14`" in brief(git, {"pyproject.toml": after})


def test_complexity_cap_comes_from_pyproject() -> None:
    git: Git = working_tree("1\t0\tsrc/app.py\x00", extra={**python_change("src/app.py"), complexity_command(["src/app.py"]): Result(0, "")})
    files: dict[str, str] = {"src/app.py": "", ".complexipy_cache/review-brief.json": "[]", "pyproject.toml": "[tool.complexipy]\nmax-complexity-allowed = 20\n"}
    assert "## Complexity: highest in changed files (cap 20)" in brief(git, files)


def test_clean_coverage_and_mutation_reports() -> None:
    git: Git = working_tree("1\t0\tsrc/app.py\x00", extra={**python_change("src/app.py"), complexity_command(["src/app.py"]): Result(0, "")})
    files: dict[str, str] = {
        "src/app.py": "",
        ".complexipy_cache/review-brief.json": "[]",
        "coverage.xml": '<coverage><class filename="src/app.py"/></coverage>',
        "mutants/survivors.txt": "    other.x_g__mutmut_1: survived\n",
    }
    text: str = brief(git, files)
    assert "## Coverage: every changed module has a coverage record" in text
    assert "## Mutation: no survivors in changed modules (from the last mutation run)" in text


def test_full_brief_text() -> None:
    """The whole brief, pinned: every heading and line format is part of what the user reads."""
    diff: str = f"@@ -0,0 +1,3 @@\n+run(x)  {NOQA}: S603\n+import os  {NOQA}: F401\n+import re  {NOQA}: F401\n"
    git: Git = working_tree(
        "3\t0\tsrc/app.py\x001\t1\tpyproject.toml\x000\t2\tsrc/old.py\x00",
        untracked="notes.txt\x00",
        extra={
            **python_change("src/app.py"),
            ("git", "diff", "-U0", "--no-color", "--no-ext-diff", "HEAD", "--", "src/app.py"): Result(0, diff),
            BASE_PYPROJECT: Result(0, '[project]\ndependencies = ["requests>=2"]\n'),
            complexity_command(["src/app.py"]): Result(0, ""),
        },
    )
    report: list[dict[str, object]] = [{"path": "src\\app.py", "function_name": "b", "complexity": 3}, {"path": "src/app.py", "function_name": "a", "complexity": 3}]
    files: dict[str, str] = {
        "src/app.py": f"run(x)  {NOQA}: S603\nimport os  {NOQA}: F401\nimport re  {NOQA}: F401\n",
        "pyproject.toml": '[project]\ndependencies = ["httpx>=0.27"]\n',
        "notes.txt": "one\n",
        "suppressions.toml": '[[suppression]]\npath = "src/app.py"\ncode = "S603"\nreason = "fixed argv"\n',
        ".complexipy_cache/review-brief.json": json.dumps(report),
        "coverage.xml": "<coverage/>",
        "mutants/survivors.txt": "    src.app.x_f__mutmut_1: survived\n    src.app.xǁAppǁrun__mutmut_2: survived\n",
    }
    assert brief(git, files) == "\n".join(
        [
            "# Review brief: changes since HEAD",
            "",
            "## Size: 4 files, +5 / -3",
            "- `notes.txt` +1 / -0 (new, untracked)",
            "- `pyproject.toml` +1 / -1",
            "- `src/app.py` +3 / -0",
            "- `src/old.py` +0 / -2",
            "",
            "## Gate files touched: 1",
            "- `pyproject.toml`",
            "",
            "## Dependencies: +1 / -1",
            "- added `httpx>=0.27`",
            "- removed `requests>=2`",
            "",
            "## Suppressions added: 3 (2 unapproved)",
            "- `src/app.py:2` `noqa: F401` UNAPPROVED",
            "- `src/app.py:3` `noqa: F401` UNAPPROVED",
            "- `src/app.py:1` `noqa: S603` approved",
            "",
            "## Complexity: highest in changed files (cap 15)",
            "- `src/app.py` `a` 3",
            "- `src/app.py` `b` 3",
            "",
            "## Coverage: 1 changed module without a coverage record",
            "- `src/app.py`",
            "",
            "## Mutation: 2 survivors in changed modules (from the last mutation run)",
            "- `src/app.py` 2",
        ]
    )


def test_only_added_lines_of_a_tracked_file_are_listed() -> None:
    diff: str = "@@ -1,0 +2 @@\n+y: int = 2\n"
    git: Git = working_tree(
        "1\t0\tsrc/app.py\x00",
        extra={**python_change("src/app.py"), ("git", "diff", "-U0", "--no-color", "--no-ext-diff", "HEAD", "--", "src/app.py"): Result(0, diff), complexity_command(["src/app.py"]): Result(1, "")},
    )
    assert "## Suppressions added: none" in brief(git, {"src/app.py": f"import os  {NOQA}: F401\ny: int = 2\n"})


def test_directive_text_in_a_string_and_notebook_suppressions() -> None:
    nb_diff: str = f'@@ -0,0 +1 @@\n+  "source": ["import os  {NOQA}: F401"]\n'
    git: Git = working_tree(
        "1\t0\tnb.ipynb\x001\t0\tsrc/app.py\x00",
        extra={
            **python_change("src/app.py"),
            **python_change("nb.ipynb"),
            ("git", "diff", "-U0", "--no-color", "--no-ext-diff", "HEAD", "--", "src/app.py"): Result(0, '@@ -0,0 +1 @@\n+s: str = "# type: ignore"\n'),
            ("git", "diff", "-U0", "--no-color", "--no-ext-diff", "HEAD", "--", "nb.ipynb"): Result(0, nb_diff),
            complexity_command(["src/app.py"]): Result(1, ""),
        },
    )
    files: dict[str, str] = {"src/app.py": 's: str = "# type: ignore"\n', "nb.ipynb": f'  "source": ["import os  {NOQA}: F401"]\n'}
    assert "## Suppressions added: 1 (1 unapproved)\n- `nb.ipynb:1` `noqa: F401` UNAPPROVED" in brief(git, files)


def test_an_invalid_allow_list_approves_nothing() -> None:
    git: Git = working_tree(
        "1\t0\tsrc/app.py\x00",
        extra={
            **python_change("src/app.py"),
            ("git", "diff", "-U0", "--no-color", "--no-ext-diff", "HEAD", "--", "src/app.py"): Result(0, f"@@ -0,0 +1 @@\n+run(x)  {NOQA}: S603\n"),
            complexity_command(["src/app.py"]): Result(1, ""),
        },
    )
    files: dict[str, str] = {"src/app.py": f"run(x)  {NOQA}: S603\n", "suppressions.toml": '[[suppression]]\npath = "src/app.py"\n'}
    assert "- `src/app.py:1` `noqa: S603` UNAPPROVED" in brief(git, files)


def test_pyproject_missing_at_the_base_adds_every_dependency() -> None:
    git: Git = working_tree("3\t0\tpyproject.toml\x00", extra={BASE_PYPROJECT: Result(128, "fatal: path 'pyproject.toml' does not exist in 'HEAD'")})
    assert "## Dependencies: +1 / -0\n- added `httpx>=0.27`" in brief(git, {"pyproject.toml": '[project]\ndependencies = ["httpx>=0.27"]\n'})


def test_before_the_first_commit_the_index_is_not_a_base() -> None:
    git: Git = Git(
        {
            HEAD: Result(1, ""),
            ("git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"): Result(0, "pyproject.toml\x00"),
            ("git", "show", ":./pyproject.toml"): Result(0, '[project]\ndependencies = ["httpx>=0.27"]\n'),
        }
    )
    assert "## Dependencies: +1 / -0\n- added `httpx>=0.27`" in brief(git, {"pyproject.toml": '[project]\ndependencies = ["httpx>=0.27"]\n'})


def test_project_without_dependencies_key() -> None:
    git: Git = working_tree("1\t0\tpyproject.toml\x00", extra={BASE_PYPROJECT: Result(0, "")})
    assert "## Dependencies: no change" in brief(git, {"pyproject.toml": '[project]\nname = "x"\n'}).splitlines()


@pytest.mark.parametrize(
    ("pyproject", "cap"),
    [('[project]\nname = "x"\n', 15), ("[tool]\ncomplexipy = 3\n", 15), ('[tool.complexipy]\nmax-complexity-allowed = "x"\n', 15)],
    ids=["no-tool-table", "settings-not-a-table", "cap-not-an-integer"],
)
def test_malformed_complexity_settings_fall_back_to_the_default(pyproject: str, cap: int) -> None:
    git: Git = working_tree("1\t0\tsrc/app.py\x00", extra={**python_change("src/app.py"), complexity_command(["src/app.py"]): Result(0, "")})
    files: dict[str, str] = {"src/app.py": "", ".complexipy_cache/review-brief.json": "[]", "pyproject.toml": pyproject}
    assert f"(cap {cap})" in brief(git, files)


def test_paths_with_tabs_and_spaces_survive_numstat() -> None:
    git: Git = working_tree("1\t0\ta\tb.txt\x002\t0\t lead.txt\x00")
    text: str = brief(git, {})
    assert "- `a\tb.txt` +1 / -0" in text
    assert "- ` lead.txt` +2 / -0" in text


def test_a_deleted_module_does_not_stop_the_analysis_of_the_next() -> None:
    git: Git = working_tree("0\t3\ta_gone.py\x001\t0\tb_app.py\x00", extra={**python_change("b_app.py"), complexity_command(["b_app.py"]): Result(0, "")})
    text: str = brief(git, {"b_app.py": "", ".complexipy_cache/review-brief.json": json.dumps([{"path": "b_app.py", "function_name": "f", "complexity": 1}])})
    assert "- `b_app.py` `f` 1" in text


def test_survivors_in_an_x_named_module() -> None:
    git: Git = working_tree("1\t0\tsrc/x_util.py\x00", extra={**python_change("src/x_util.py"), complexity_command(["src/x_util.py"]): Result(1, "")})
    files: dict[str, str] = {"src/x_util.py": "", "mutants/survivors.txt": "    src.x_util.x_f__mutmut_1: survived\n"}
    assert "## Mutation: 1 survivors in changed modules (from the last mutation run)\n- `src/x_util.py` 1" in brief(git, files)


def test_numstat_failure_carries_git_output() -> None:
    error_info: pytest.ExceptionInfo[GitError]
    with pytest.raises(GitError) as error_info:
        brief(Git({HEAD: Result(0, "abc\n")}), {})
    assert error_info.value.result.output == "fatal: unexpected git diff -z --numstat --no-renames --relative HEAD"


def test_main_reads_files_through_the_given_reader(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([], working_tree("", untracked="notes.txt\x00"), files_reader({"notes.txt": "a\n"})) == 0
    assert "- `notes.txt` +1 / -0 (new, untracked)" in capsys.readouterr().out


def test_help_shows_the_docstring_and_option(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("COLUMNS", "200")
    exit_info: pytest.ExceptionInfo[SystemExit]
    with pytest.raises(SystemExit) as exit_info:
        main(["--help"], Git({}), files_reader({}))
    assert exit_info.value.code == 0
    out: str = capsys.readouterr().out
    assert "\n    uv run python -m tools.review_brief --base origin/main (this branch's changes)\n" in out
    assert re.search(r"--base BASE +describe the changes since the merge base with this ref instead of HEAD\n", out)


def test_empty_sections_are_whole_lines() -> None:
    git: Git = working_tree("1\t0\tREADME.md\x00")
    assert brief(git, {"README.md": "x\n"}).splitlines() == [
        "# Review brief: changes since HEAD",
        "",
        "## Size: 1 files, +1 / -0",
        "- `README.md` +1 / -0",
        "",
        "## Gate files touched: none",
        "",
        "## Dependencies: no change",
        "",
        "## Suppressions added: none",
        "",
        "## Complexity: no changed Python modules",
        "",
        "## Coverage: no coverage.xml (run the tests with --cov)",
        "",
        "## Mutation: no mutants/survivors.txt (run bash tools/mutation.sh)",
    ]


def test_report_states_are_whole_lines() -> None:
    git: Git = working_tree("1\t0\tsrc/a.py\x001\t0\tsrc/b.py\x00", extra={**python_change("src/a.py"), **python_change("src/b.py"), complexity_command(["src/a.py", "src/b.py"]): Result(1, "")})
    files: dict[str, str] = {"src/a.py": "", "src/b.py": "", "coverage.xml": "<coverage/>", "mutants/survivors.txt": ""}
    lines: list[str] = brief(git, files).splitlines()
    assert "## Complexity: not measured (complexipy did not run)" in lines
    assert "## Coverage: 2 changed modules without a coverage record" in lines
    assert "## Mutation: no survivors in changed modules (from the last mutation run)" in lines
    git = working_tree("1\t0\tsrc/a.py\x00", extra={**python_change("src/a.py"), complexity_command(["src/a.py"]): Result(1, "")})
    assert "## Coverage: every changed module has a coverage record" in brief(git, {"src/a.py": "", "coverage.xml": '<class filename="src/a.py"/>'}).splitlines()


def test_untracked_module_suppressions_are_listed() -> None:
    git: Git = working_tree(
        "",
        untracked="src/new.py\x00",
        extra={("git", "ls-files", "-z", "--others", "--exclude-standard", "--", "src/new.py"): Result(0, "src/new.py\x00"), complexity_command(["src/new.py"]): Result(1, "")},
    )
    assert "- `src/new.py:1` `noqa: F401` UNAPPROVED" in brief(git, {"src/new.py": f"import os  {NOQA}: F401\n"})


def test_complexity_ties_are_ordered_by_path() -> None:
    report: list[dict[str, object]] = [{"path": "b.py", "function_name": "a", "complexity": 4}, {"path": "a.py", "function_name": "z", "complexity": 4}]
    git: Git = working_tree("1\t0\ta.py\x001\t0\tb.py\x00", extra={**python_change("a.py"), **python_change("b.py"), complexity_command(["a.py", "b.py"]): Result(0, "")})
    text: str = brief(git, {"a.py": "", "b.py": "", ".complexipy_cache/review-brief.json": json.dumps(report)})
    assert "- `a.py` `z` 4\n- `b.py` `a` 4" in text


def test_over_cap_functions_are_shown() -> None:
    """An over-cap function makes complexipy exit 1; the brief must still show it."""
    report: list[dict[str, object]] = [{"path": "src/app.py", "function_name": "tangled", "complexity": 23}]
    git: Git = working_tree("1\t0\tsrc/app.py\x00", extra={**python_change("src/app.py"), complexity_command(["src/app.py"]): Result(0, "")})
    text: str = brief(git, {"src/app.py": "", ".complexipy_cache/review-brief.json": json.dumps(report)})
    assert "- `src/app.py` `tangled` 23" in text.splitlines()


def test_mutation_counts_only_survivors() -> None:
    """The results file also lists timeouts, which are caught mutants, not survivors."""
    git: Git = working_tree("1\t0\tsrc/app.py\x00", extra={**python_change("src/app.py"), complexity_command(["src/app.py"]): Result(1, "")})
    # A caught mutant listed first must not stop the count; trailing spaces are not part of the status.
    survivors: str = "    src.app.x_f__mutmut_2: timeout\n    src.app.x_f__mutmut_1: survived  \n    src.app.x_f__mutmut_3: suspicious\n"
    text: str = brief(git, {"src/app.py": "", "mutants/survivors.txt": survivors})
    assert "## Mutation: 1 survivors in changed modules (from the last mutation run)\n- `src/app.py` 1" in text
