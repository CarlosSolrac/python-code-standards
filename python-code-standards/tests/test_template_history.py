"""Tests for recording the digest of every template version the setup script has written."""

from __future__ import annotations

import json
import runpy
import sys
import tomllib
from collections.abc import Sequence
from pathlib import Path

import pytest

from skill.tools.hooks.stop_gate import GitError, Result
from skill.tools.setup_files import digest, table_digest
from skill.tools.template_history import embed, known_digests, main, script_versions, templates

SCRIPT: str = """\
#!/usr/bin/env bash
if absent pyproject.toml; then
    sed "s|x|y|" >pyproject.toml <<'TOML'
[project]
name = "example-project"

[tool.ruff]
line-length = 220
TOML
fi

write_file .gitignore <<'IGNORE'
.venv/
IGNORE

write_file tests/.gitkeep </dev/null

cat >"$WORK/hashes.json" <<'HASHEOF'
{}
HASHEOF
"""


def test_templates_reads_every_file_the_script_writes() -> None:
    assert templates(SCRIPT) == {
        "pyproject.toml": '[project]\nname = "example-project"\n\n[tool.ruff]\nline-length = 220\n',
        ".gitignore": ".venv/\n",
        "tests/.gitkeep": "",
    }


def test_known_digests_unions_every_version() -> None:
    newer: str = SCRIPT.replace(".venv/\n", ".venv/\ndist/\n").replace("line-length = 220", "line-length = 100")
    digests: dict[str, dict[str, list[str]]] = known_digests([SCRIPT, newer, SCRIPT], recorded={})
    assert digests["files"] == {
        ".gitignore": sorted([digest(".venv/\n"), digest(".venv/\ndist/\n")]),
        "tests/.gitkeep": [digest("")],
    }
    assert digests["tables"] == {"tool.ruff": sorted([table_digest({"line-length": 220}), table_digest({"line-length": 100})])}


class FakeGit:
    """Answers ``git log`` with two commits and ``git show`` with a script per commit."""

    def __init__(self, failing: str = "") -> None:
        """Fail any command containing ``failing``."""
        self.failing: str = failing
        self.commands: list[tuple[str, ...]] = []

    def __call__(self, command: Sequence[str]) -> Result:
        """Run one fake git command."""
        self.commands.append(tuple(command))
        if self.failing and self.failing in command:
            return Result(128, "fatal: bad")
        if command[1] == "log":
            return Result(0, "aaa\nbbb\n")
        return Result(0, f"script at {command[2]}")


def test_script_versions_reads_each_commit_of_the_script() -> None:
    git: FakeGit = FakeGit()
    assert script_versions(git, "skill/x.sh") == ["script at aaa:./skill/x.sh", "script at bbb:./skill/x.sh"]
    assert git.commands == [("git", "log", "--format=%H", "--", "skill/x.sh"), ("git", "show", "aaa:./skill/x.sh"), ("git", "show", "bbb:./skill/x.sh")]


@pytest.mark.parametrize("failing", ["log", "bbb:./skill/x.sh"])
def test_script_versions_fails_closed(failing: str) -> None:
    error: pytest.ExceptionInfo[GitError]
    with pytest.raises(GitError) as error:
        script_versions(FakeGit(failing), "skill/x.sh")
    assert error.value.result == Result(128, "fatal: bad")


def test_embed_replaces_only_the_digest_heredoc() -> None:
    result: str = embed(SCRIPT, {"files": {"a": ["1"]}, "tables": {}})
    assert result == SCRIPT.replace("<<'HASHEOF'\n{}\n", "<<'HASHEOF'\n" + json.dumps({"files": {"a": ["1"]}, "tables": {}}, indent=1, sort_keys=True) + "\n")


def test_main_embeds_history_and_the_working_copy(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    script: Path = tmp_path / "setup.sh"
    script.write_text(SCRIPT.replace(".venv/\n", ".venv/\nbuild/\n"), encoding="utf-8", newline="")

    def git(command: Sequence[str]) -> Result:
        return Result(0, "aaa\n") if command[1] == "log" else Result(0, SCRIPT)

    assert main([], run=git, script=script) == 0
    embedded: dict[str, dict[str, list[str]]] = json.loads(script.read_text(encoding="utf-8").split("<<'HASHEOF'\n")[1].split("\nHASHEOF\n")[0])
    assert embedded["files"][".gitignore"] == sorted([digest(".venv/\n"), digest(".venv/\nbuild/\n")])
    assert embedded["tables"]["tool.ruff"] == [table_digest(tomllib.loads("line-length = 220"))]
    assert capsys.readouterr().out == f"updated {script}\n"
    assert main([], run=git, script=script) == 0
    assert capsys.readouterr().out == f"{script} is up to date\n"


def test_runs_as_a_module(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """Run with ``python -m``, the module exits with ``main``'s status."""
    monkeypatch.setattr(sys, "argv", ["template_history", "--help"])
    # runpy warns when the module it runs as __main__ is already imported.
    monkeypatch.delitem(sys.modules, "skill.tools.template_history")
    exit_info: pytest.ExceptionInfo[SystemExit]
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module("skill.tools.template_history", run_name="__main__")
    assert exit_info.value.code == 0
    assert "HASHEOF" in capsys.readouterr().out


def test_main_keeps_digests_already_embedded(tmp_path: Path) -> None:
    """A shallow clone has no history, so regenerating there must not forget earlier versions."""
    script: Path = tmp_path / "setup.sh"
    recorded: dict[str, dict[str, list[str]]] = {"files": {".gitignore": ["old-file"]}, "tables": {"tool.ruff": ["old-table"]}}
    script.write_text(embed(SCRIPT, recorded), encoding="utf-8", newline="")

    def shallow(_command: Sequence[str]) -> Result:
        return Result(0, "")

    main([], run=shallow, script=script)
    embedded: dict[str, dict[str, list[str]]] = json.loads(script.read_text(encoding="utf-8").split("<<'HASHEOF'\n")[1].split("\nHASHEOF\n")[0])
    assert embedded["files"][".gitignore"] == sorted([digest(".venv/\n"), "old-file"])
    assert embedded["tables"]["tool.ruff"] == sorted([table_digest({"line-length": 220}), "old-table"])


def test_main_reads_the_history_of_the_script_it_updates(tmp_path: Path) -> None:
    script: Path = tmp_path / "setup.sh"
    script.write_text(SCRIPT, encoding="utf-8", newline="")
    commands: list[tuple[str, ...]] = []

    def git(command: Sequence[str]) -> Result:
        commands.append(tuple(command))
        return Result(0, "")

    main([], run=git, script=script)
    assert commands == [("git", "log", "--format=%H", "--", script.as_posix())]


def test_help_shows_the_usage_verbatim(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["--help"])
    assert "Usage (from the directory holding ``pyproject.toml``):\n    uv run python -m skill.tools.template_history\n" in capsys.readouterr().out


def test_known_digests_accepts_a_pyproject_without_tool_tables() -> None:
    script: str = "sed x >pyproject.toml <<'TOML'\n[project]\nname = \"x\"\nTOML\n"
    assert known_digests([script], recorded={}) == {"files": {}, "tables": {}}


def test_templates_follow_bash_heredoc_rules() -> None:
    """The opener may end in spaces; only a line that is exactly the delimiter closes the body."""
    script: str = "write_file a.txt <<'IGNORE'  \nkeep\nIGNORE  \nIGNOREX\nIGNORE\n"
    assert templates(script) == {"a.txt": "keep\nIGNORE  \nIGNOREX\n"}


def test_embed_fills_an_empty_heredoc() -> None:
    script: str = "cat <<'HASHEOF'\nHASHEOF\necho done\n"
    assert embed(script, {"files": {}, "tables": {}}) == 'cat <<\'HASHEOF\'\n{\n "files": {},\n "tables": {}\n}\nHASHEOF\necho done\n'
