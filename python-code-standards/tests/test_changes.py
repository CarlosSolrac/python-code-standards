"""Tests for the git helpers shared by the change-scoped checks."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from skill.tools.changes import added_lines, base_commit, changed_files
from skill.tools.hooks.stop_gate import GitError, Result


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


def test_base_commit_defaults_to_head() -> None:
    assert base_commit(None, Git({("git", "rev-parse", "--verify", "--quiet", "HEAD"): Result(0, "abc123\n")})) == "HEAD"


def test_base_commit_is_empty_before_the_first_commit() -> None:
    """A repository with no commit yet (the setup script stages, then commits) has nothing to compare against.

    ``rev-parse --verify --quiet`` exits 1, silently, when ``HEAD`` is unborn.
    """
    assert base_commit(None, Git({("git", "rev-parse", "--verify", "--quiet", "HEAD"): Result(1, "")})) == ""


def test_base_commit_raises_when_git_itself_fails() -> None:
    """A broken repository (exit 128) is not "no commit yet"; reading it so would skip the check."""
    git: Git = Git({("git", "rev-parse", "--verify", "--quiet", "HEAD"): Result(128, "fatal: bad config line 11 in file .git/config")})
    with pytest.raises(GitError):
        base_commit(None, git)


def test_base_commit_is_the_merge_base_with_the_given_ref() -> None:
    """Comparing against the merge base ignores commits the base gained since the branch forked."""
    git: Git = Git({("git", "merge-base", "origin/main", "HEAD"): Result(0, "abc123\n")})
    assert base_commit("origin/main", git) == "abc123"


def test_base_commit_raises_when_git_fails() -> None:
    with pytest.raises(GitError):
        base_commit("origin/missing", Git({}))


def test_changed_files_lists_existing_paths_since_the_commit() -> None:
    git: Git = Git({("git", "diff", "-z", "--name-only", "--relative", "--diff-filter=d", "abc123"): Result(0, "b.py\0a.py\0")})
    assert changed_files("abc123", git) == ["a.py", "b.py"]


DIFF: str = """diff --git a/m.py b/m.py
--- a/m.py
+++ b/m.py
@@ -3,0 +4,2 @@ def f():
+    x = 1  # first
+    y = 2
@@ -10 +12 @@
-old
+new
"""


def test_added_lines_of_a_tracked_file_come_from_the_diff() -> None:
    git: Git = Git(
        {
            ("git", "ls-files", "-z", "--others", "--exclude-standard", "--", "m.py"): Result(0, ""),
            ("git", "diff", "-U0", "--no-color", "--no-ext-diff", "abc123", "--", "m.py"): Result(0, DIFF),
        }
    )
    assert added_lines("m.py", "abc123", git, lambda _: "unused") == [(4, "    x = 1  # first"), (5, "    y = 2"), (12, "new")]


def test_every_line_of_an_untracked_file_is_added() -> None:
    git: Git = Git({("git", "ls-files", "-z", "--others", "--exclude-standard", "--", "new.py"): Result(0, "new.py\0")})
    assert added_lines("new.py", "HEAD", git, lambda _: "a = 1\nb = 2\n") == [(1, "a = 1"), (2, "b = 2")]


def test_every_line_is_added_before_the_first_commit() -> None:
    assert added_lines("staged.py", "", Git({}), lambda _: "a = 1\n") == [(1, "a = 1")]


def test_added_lines_raises_when_the_diff_fails() -> None:
    git: Git = Git({("git", "ls-files", "-z", "--others", "--exclude-standard", "--", "m.py"): Result(0, "")})
    with pytest.raises(GitError):
        added_lines("m.py", "abc123", git, lambda _: "")
