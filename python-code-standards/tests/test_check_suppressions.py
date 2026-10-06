"""Tests for the check that a change adds no unapproved suppression.

A missed suppression is silent, so the allowed cases are asserted as
explicitly as the reported ones.
"""

from __future__ import annotations

import re
import runpy
import sys
from collections.abc import Sequence
from pathlib import Path

import pytest

from skill.tools.check_suppressions import Allowed, Suppression, load_allowed, main, read_file, suppressions_in
from skill.tools.hooks.stop_gate import Result

NOQA: str = "# " + "noqa"  # split so this file holds no suppression of its own


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("x = 1", []),
        (f"import os  {NOQA}: F401", [Suppression("noqa", "F401")]),
        (f"run(cmd)  {NOQA}: S603 -- fixed argv", [Suppression("noqa", "S603")]),
        (f"x  {NOQA}: E501, S101", [Suppression("noqa", "E501"), Suppression("noqa", "S101")]),
        # Ruff also accepts spaces between codes; each one needs its own approval.
        (f"x  {NOQA}: S603 S607", [Suppression("noqa", "S603"), Suppression("noqa", "S607")]),
        (f"x  {NOQA}", [Suppression("noqa", "")]),
        ("x  # type: ignore[arg-type]", [Suppression("type: ignore", "arg-type")]),
        ("x  # type: ignore", [Suppression("type: ignore", "")]),
        ("x  # pyright: ignore[reportPrivateUsage, reportUnknownMemberType]", [Suppression("pyright: ignore", "reportPrivateUsage"), Suppression("pyright: ignore", "reportUnknownMemberType")]),
        ("if x:  # pragma: no cover", [Suppression("pragma", "no cover")]),
        ("x  # Pragma: No Cover", [Suppression("pragma", "no cover")]),
        # File-level and tool-specific directives silence whole files or functions.
        ("# ruff: noqa", [Suppression("ruff: noqa", "")]),
        ("# ruff: noqa: E501", [Suppression("ruff: noqa", "E501")]),
        ("# mypy: ignore-errors", [Suppression("mypy", "ignore-errors")]),
        ("# pyright: basic", [Suppression("pyright", "basic")]),
        ("# pyright: reportPrivateUsage=false", [Suppression("pyright", "reportPrivateUsage=false")]),
        ("def f():  # complexipy: ignore", [Suppression("complexipy", "ignore")]),
        # A setting's code is its whole value, so approving one value never approves another.
        ('# mypy: disable-error-code = "arg-type"', [Suppression("mypy", 'disable-error-code = "arg-type"')]),
        ('# mypy: disable-error-code = "arg-type, assignment"', [Suppression("mypy", 'disable-error-code = "arg-type, assignment"')]),
        # Ruff honors flake8's file-level form; coverage.py honors no-branch.
        ("# flake8: noqa", [Suppression("flake8: noqa", "")]),
        ("# flake8: noqa: S101", [Suppression("flake8: noqa", "S101")]),
        ("if x:  # pragma: no branch", [Suppression("pragma", "no branch")]),
        # coverage.py's pragmas work without the colon; compact spellings are the same directive.
        ("if x:  # pragma no cover", [Suppression("pragma", "no cover")]),
        ("if x:  # pragma no branch", [Suppression("pragma", "no branch")]),
        ("x  # type:ignore[arg-type]", [Suppression("type: ignore", "arg-type")]),
        ("x  # pyright:ignore[reportPrivateUsage]", [Suppression("pyright: ignore", "reportPrivateUsage")]),
        ("x  # ruff:noqa: E501", [Suppression("ruff: noqa", "E501")]),
        # mutmut skips a line marked this way, hiding it from mutation testing.
        ("x = 1  # pragma: no mutate", [Suppression("pragma", "no mutate")]),
        ("x = 1  # pragma no mutate", [Suppression("pragma", "no mutate")]),
    ],
    ids=[
        "none",
        "noqa",
        "noqa-reason",
        "noqa-many",
        "noqa-space-separated",
        "noqa-blanket",
        "type-ignore",
        "type-ignore-bare",
        "pyright-many",
        "pragma",
        "pragma-case",
        "ruff-file",
        "ruff-file-code",
        "mypy-file",
        "pyright-file",
        "pyright-rule-off",
        "complexipy",
        "mypy-setting-one",
        "mypy-setting-two",
        "flake8-file",
        "flake8-file-code",
        "pragma-no-branch",
        "pragma-no-cover-no-colon",
        "pragma-no-branch-no-colon",
        "type-ignore-compact",
        "pyright-ignore-compact",
        "ruff-noqa-compact",
        "pragma-no-mutate",
        "pragma-no-mutate-no-colon",
    ],
)
def test_suppressions_in(line: str, expected: list[Suppression]) -> None:
    assert suppressions_in(line) == expected


def test_label_reads_like_the_comment() -> None:
    assert Suppression("noqa", "S603").label() == "noqa: S603"
    assert Suppression("type: ignore", "arg-type").label() == "type: ignore[arg-type]"
    assert Suppression("noqa", "").label() == "noqa (blanket)"
    assert Suppression("pragma", "no cover").label() == "pragma: no cover"
    assert Suppression("pyright: ignore", "").label() == "pyright: ignore"
    assert Suppression("ruff: noqa", "").label() == "ruff: noqa (whole file)"
    assert Suppression("ruff: noqa", "E501").label() == "ruff: noqa: E501"
    assert Suppression("mypy", "ignore-errors").label() == "mypy: ignore-errors"
    assert Suppression("complexipy", "ignore").label() == "complexipy: ignore"
    assert Suppression("flake8: noqa", "").label() == "flake8: noqa (whole file)"
    assert Suppression("pragma", "no branch").label() == "pragma: no branch"


ALLOW: str = """
[[suppression]]
path = "tools/hooks/stop_gate.py"
code = "S603"
reason = "fixed argv, never a shell"
"""


def test_load_allowed(tmp_path: Path) -> None:
    allow: Path = tmp_path / "suppressions.toml"
    assert load_allowed(allow) == Allowed(set())
    allow.write_text(ALLOW, encoding="utf-8")
    assert load_allowed(allow) == Allowed({("tools/hooks/stop_gate.py", "S603")})


@pytest.mark.parametrize("entry", ['path = "a.py"\ncode = "S603"', 'path = "a.py"\ncode = ""\nreason = "r"', 'path = "a.py"\ncode = "S603"\nreason = " "'])
def test_load_allowed_rejects_an_entry_without_path_code_and_reason(tmp_path: Path, entry: str) -> None:
    allow: Path = tmp_path / "suppressions.toml"
    allow.write_text(f"[[suppression]]\n{entry}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="path, code, and reason"):
        load_allowed(allow)


def test_allowed_permits_only_listed_pairs_and_test_private_usage() -> None:
    allowed: Allowed = Allowed({("tools/hooks/stop_gate.py", "S603")})
    assert allowed.permits("tools/hooks/stop_gate.py", Suppression("noqa", "S603"))
    assert not allowed.permits("tools/hooks/stop_gate.py", Suppression("noqa", "S607"))
    assert not allowed.permits("src/app.py", Suppression("noqa", "S603"))
    assert not allowed.permits("tools/hooks/stop_gate.py", Suppression("noqa", ""))
    # SKILL.md lets unit tests suppress reportPrivateUsage per line without asking.
    assert allowed.permits("tests/test_app.py", Suppression("pyright: ignore", "reportPrivateUsage"))
    assert allowed.permits("src/test_app.py", Suppression("pyright: ignore", "reportPrivateUsage"))
    assert not allowed.permits("src/app.py", Suppression("pyright: ignore", "reportPrivateUsage"))


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


def untracked(path: str) -> dict[tuple[str, ...], Result]:
    """Return git answers saying HEAD exists and the path is untracked, so all its lines are new."""
    return {
        ("git", "rev-parse", "--verify", "--quiet", "HEAD"): Result(0, "abc123\n"),
        ("git", "ls-files", "-z", "--others", "--exclude-standard", "--", path): Result(0, f"{path}\0"),
    }


def test_new_suppression_is_reported_with_location_and_remedy(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source: str = f"x = 1\nimport os  {NOQA}: F401\n"
    status: int = main(["src/app.py"], Git(untracked("src/app.py")), lambda _: source, tmp_path / "suppressions.toml")
    assert status == 1
    out: str = capsys.readouterr().out
    assert "src/app.py:2: new suppression `noqa: F401`" in out
    assert "suppressions.toml" in out


def test_allow_listed_suppression_passes(tmp_path: Path) -> None:
    allow: Path = tmp_path / "suppressions.toml"
    allow.write_text(ALLOW, encoding="utf-8")
    source: str = f"run(cmd)  {NOQA}: S603 -- fixed argv\n"
    assert main(["tools/hooks/stop_gate.py"], Git(untracked("tools/hooks/stop_gate.py")), lambda _: source, allow) == 0


def test_space_separated_codes_need_every_approval(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Approving S603 must not also approve an S607 written beside it."""
    allow: Path = tmp_path / "suppressions.toml"
    allow.write_text(ALLOW, encoding="utf-8")
    source: str = f'subprocess.run(["tool", arg], check=True)  {NOQA}: S603 S607\n'
    assert main(["tools/hooks/stop_gate.py"], Git(untracked("tools/hooks/stop_gate.py")), lambda _: source, allow) == 1
    out: str = capsys.readouterr().out
    assert "`noqa: S607`" in out
    assert "`noqa: S603`" not in out


@pytest.mark.parametrize(
    "source",
    [
        'example: str = "# type: ignore"\n',
        f'"""Write {NOQA}: E501 to silence a long line."""\n',
        f'text: str = """\n{NOQA}: S101\n"""\n',
    ],
    ids=["string", "docstring", "multiline-string"],
)
def test_directive_text_inside_a_string_is_not_a_suppression(tmp_path: Path, source: str) -> None:
    assert main(["src/docs.py"], Git(untracked("src/docs.py")), lambda _: source, tmp_path / "suppressions.toml") == 0


def test_only_the_comment_of_a_line_is_scanned(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source: str = f's: str = "# type: ignore"  {NOQA}: E501\n'
    assert main(["src/app.py"], Git(untracked("src/app.py")), lambda _: source, tmp_path / "suppressions.toml") == 1
    out: str = capsys.readouterr().out
    assert "`noqa: E501`" in out
    assert "type: ignore" not in out


def test_untokenizable_source_falls_back_to_scanning_text(tmp_path: Path) -> None:
    """A file Python cannot tokenize (mid-edit) is scanned as text, the strict direction."""
    source: str = f's = "unterminated\nimport os  {NOQA}: F401\n'
    assert main(["src/broken.py"], Git(untracked("src/broken.py")), lambda _: source, tmp_path / "suppressions.toml") == 1


def test_notebook_is_scanned_as_text(tmp_path: Path) -> None:
    """Notebooks are JSON, so their cell source is scanned as text."""
    source: str = f'{{"cells": [{{"cell_type": "code", "source": ["import os  {NOQA}: F401"]}}]}}\n'
    assert main(["nb.ipynb"], Git(untracked("nb.ipynb")), lambda _: source, tmp_path / "suppressions.toml") == 1


def test_clean_change_passes(tmp_path: Path) -> None:
    assert main(["src/app.py"], Git(untracked("src/app.py")), lambda _: "x = 1\n", tmp_path / "suppressions.toml") == 0


def test_invalid_allow_list_fails_with_its_message(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    allow: Path = tmp_path / "suppressions.toml"
    allow.write_text('[[suppression]]\npath = "a.py"\n', encoding="utf-8")
    assert main(["src/app.py"], Git(untracked("src/app.py")), lambda _: "x = 1\n", allow) == 1
    assert "path, code, and reason" in capsys.readouterr().out


def test_base_mode_checks_every_file_changed_since_the_merge_base(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """CI passes --base and no files: the check finds the branch's changes itself."""
    diff: str = f"--- a/src/app.py\n+++ b/src/app.py\n@@ -1,0 +2 @@\n+import os  {NOQA}: F401\n"
    git: Git = Git(
        {
            ("git", "merge-base", "origin/main", "HEAD"): Result(0, "abc123\n"),
            ("git", "diff", "-z", "--name-only", "--relative", "--diff-filter=d", "abc123"): Result(0, "src/app.py\0README.md\0"),
            ("git", "ls-files", "-z", "--others", "--exclude-standard", "--", "src/app.py"): Result(0, ""),
            ("git", "diff", "-U0", "--no-color", "--no-ext-diff", "abc123", "--", "src/app.py"): Result(0, diff),
        }
    )
    # The current file, matching the diff: the suppression is a real comment on line 2.
    current: str = f"x = 1\nimport os  {NOQA}: F401\n"
    assert main(["--base", "origin/main"], git, lambda _: current, tmp_path / "suppressions.toml") == 1
    assert "src/app.py:2: new suppression `noqa: F401`" in capsys.readouterr().out


def test_git_failure_fails_closed(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--base", "origin/missing"], Git({}), lambda _: "", tmp_path / "suppressions.toml") == 1
    out: str = capsys.readouterr().out
    assert "`git merge-base origin/missing HEAD` failed, so the change cannot be checked:" in out
    assert "fatal: unexpected git merge-base" in out


def test_only_added_lines_of_a_tracked_file_count(tmp_path: Path) -> None:
    """A suppression already in the file is not the change's; only the diff's added lines are checked."""
    diff: str = "--- a/src/app.py\n+++ b/src/app.py\n@@ -1,0 +2 @@\n+y: int = 2\n"
    git: Git = Git(
        {
            ("git", "rev-parse", "--verify", "--quiet", "HEAD"): Result(0, "abc123\n"),
            ("git", "ls-files", "-z", "--others", "--exclude-standard", "--", "src/app.py"): Result(0, ""),
            ("git", "diff", "-U0", "--no-color", "--no-ext-diff", "HEAD", "--", "src/app.py"): Result(0, diff),
        }
    )
    files: dict[str, str] = {"src/app.py": f"import os  {NOQA}: F401\ny: int = 2\n"}
    assert main(["src/app.py"], git, files.__getitem__, tmp_path / "suppressions.toml") == 0


def test_reads_the_checked_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    files: dict[str, str] = {"src/app.py": f"import os  {NOQA}: F401\n"}
    assert main(["src/app.py"], Git(untracked("src/app.py")), files.__getitem__, tmp_path / "suppressions.toml") == 1
    assert "src/app.py:1: new suppression `noqa: F401`" in capsys.readouterr().out


@pytest.mark.parametrize(
    "path",
    ["tests/helpers.py", r"tests\helpers.py", r"src\test_app.py", "pkg/tests/conftest.py"],
    ids=["tests-dir", "tests-dir-windows", "test-file-windows", "nested-tests-dir"],
)
def test_test_files_may_suppress_private_usage(path: str) -> None:
    assert Allowed(set()).permits(path, Suppression("pyright: ignore", "reportPrivateUsage"))


@pytest.mark.parametrize("path", ["src/app.py", "src/contest.py", "latest/app.py"], ids=["source", "test-like-name", "test-like-dir"])
def test_source_files_may_not_suppress_private_usage(path: str) -> None:
    assert not Allowed(set()).permits(path, Suppression("pyright: ignore", "reportPrivateUsage"))


def test_file_setting_label_reads_like_the_comment() -> None:
    assert Suppression("pyright", "basic").label() == "pyright: basic"


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ('[[suppression]]\npath = "a.py"\ncode = "S603"\nreason = "r"\n\n[[suppression]]\npath = "b.py"\n', "entry 2 needs"),
        ('suppression = ["a.py"]\n', "entry 1 needs"),
    ],
    ids=["second-entry-numbered", "entry-not-a-table"],
)
def test_load_allowed_names_the_bad_entry(tmp_path: Path, text: str, message: str) -> None:
    allow: Path = tmp_path / "suppressions.toml"
    allow.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        load_allowed(allow)


def test_load_allowed_ignores_a_non_list_suppression_key(tmp_path: Path) -> None:
    """A malformed key approves nothing, which is the safe direction."""
    allow: Path = tmp_path / "suppressions.toml"
    allow.write_text('suppression = "oops"\n', encoding="utf-8")
    assert load_allowed(allow) == Allowed(set())


def test_help_shows_the_module_docstring_and_option_help(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("COLUMNS", "200")
    exit_info: pytest.ExceptionInfo[SystemExit]
    with pytest.raises(SystemExit) as exit_info:
        main(["--help"], Git({}), lambda _: "", Path("suppressions.toml"))
    assert exit_info.value.code == 0
    out: str = capsys.readouterr().out
    assert '\n    [[suppression]]\n    path = "tools/hooks/stop_gate.py"\n' in out
    assert re.search(r"--base BASE +compare against the merge base with this ref instead of HEAD\n", out)
    assert re.search(r"files +files to check; default: every file changed since --base\n", out)


def test_read_file(tmp_path: Path) -> None:
    source: Path = tmp_path / "app.py"
    source.write_text("x: int = 1\n", encoding="utf-8")
    assert read_file(str(source)) == "x: int = 1\n"


def test_runs_as_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run for real outside any repository: git fails, so the check fails closed."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    (tmp_path / "app.py").write_text(f"import os  {NOQA}: F401\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["check_suppressions", "app.py"])
    # runpy re-executes the module; an already-imported copy would trigger a RuntimeWarning.
    monkeypatch.delitem(sys.modules, "skill.tools.check_suppressions", raising=False)
    exit_info: pytest.ExceptionInfo[SystemExit]
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module("skill.tools.check_suppressions", run_name="__main__")
    assert exit_info.value.code == 1
