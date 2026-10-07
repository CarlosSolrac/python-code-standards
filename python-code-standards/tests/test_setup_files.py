"""Tests for installing the setup script's staged templates into a repository.

Every path that replaces a file is a place where a bug loses a user's edits, so
which files are replaced, and which are only reported, is asserted exactly.
"""

from __future__ import annotations

import json
import runpy
import sys
import tomllib
from pathlib import Path

import pytest

from skill.tools.setup_files import RewriteError, Status, backup, digest, file_status, main, missing_dev_tools, rewrite_tables, table_digest, table_status

BASELINE: str = """\
[project]
name = "example"

[dependency-groups]
dev = ["ruff>=0.14", "mypy>=1.18"]

[tool.ruff]
line-length = 220

[tool.ruff.lint]
# The house rules.
select = ["E"]

[tool.mypy]
strict = true
"""


def test_digest_ignores_line_endings() -> None:
    assert digest("a\r\nb\n") == digest("a\nb\n")
    assert digest("a\n") != digest("b\n")


def test_table_digest_ignores_formatting() -> None:
    assert table_digest(tomllib.loads("[t]\na = 1\nb = 2\n")["t"]) == table_digest(tomllib.loads("[t]\nb = 2\na    = 1 # same\n")["t"])
    assert table_digest({"a": 1}) != table_digest({"a": 2})


@pytest.mark.parametrize(
    ("current", "expected"),
    [(None, Status.MISSING), ("new\n", Status.CURRENT), ("new\r\n", Status.CURRENT), ("old\n", Status.OUTDATED), ("mine\n", Status.EDITED)],
    ids=["missing", "current", "current-with-crlf", "older-version", "edited"],
)
def test_file_status(current: str | None, expected: Status) -> None:
    assert file_status(current, "new\n", {digest("old\n")}) is expected


@pytest.mark.parametrize(
    ("current", "expected"),
    [(None, Status.MISSING), ({"a": 2}, Status.CURRENT), ({"a": 1}, Status.OUTDATED), ({"a": 3}, Status.EDITED)],
    ids=["missing", "current", "older-version", "edited"],
)
def test_table_status(current: object, expected: Status) -> None:
    assert table_status(current, {"a": 2}, {table_digest({"a": 1})}) is expected


def test_rewrite_replaces_a_table_and_its_subtables_and_keeps_the_rest() -> None:
    project: str = '[project]\nname = "mine"  # keep this\n\n[tool.ruff]\nline-length = 100\n\n[tool.ruff.lint]\nselect = ["ALL"]\n\n[tool.black]\nx = 1\n'
    result: str = rewrite_tables(project, BASELINE, {"ruff"})
    assert result == '[project]\nname = "mine"  # keep this\n\n[tool.ruff]\nline-length = 220\n\n[tool.ruff.lint]\n# The house rules.\nselect = ["E"]\n\n[tool.black]\nx = 1\n'


def test_rewrite_appends_a_missing_table() -> None:
    result: str = rewrite_tables('[project]\nname = "mine"\n', BASELINE, {"mypy"})
    assert result == '[project]\nname = "mine"\n\n[tool.mypy]\nstrict = true\n'


def test_rewrite_gathers_a_table_split_across_the_file() -> None:
    project: str = "[tool.ruff]\nline-length = 1\n\n[tool.black]\nx = 1\n\n[tool.ruff.lint]\nselect = []\n"
    result: str = rewrite_tables(project, BASELINE, {"ruff"})
    assert result == '[tool.ruff]\nline-length = 220\n\n[tool.ruff.lint]\n# The house rules.\nselect = ["E"]\n\n[tool.black]\nx = 1\n'


@pytest.mark.parametrize(
    "project",
    [
        "[tool]\nruff = { line-length = 1 }\n",
        '[project]\nname = "x"\n[tool.ruff]\nline-length = 1\n[project.urls]\nhome = """\n[tool.ruff.lint]\n"""\n',
        '[project]\ndescription = """\n[tool.ruff]\n[tool.black]\n"""\n',
    ],
    ids=["dotted-key-definition", "header-inside-a-string", "header-inside-a-string-still-parses"],
)
def test_rewrite_refuses_what_it_cannot_swap_in_place(project: str) -> None:
    with pytest.raises(RewriteError):
        rewrite_tables(project, BASELINE, {"ruff"})


def test_missing_dev_tools_compares_normalized_names() -> None:
    project: dict[str, object] = {"dependency-groups": {"dev": ["Ruff==0.16", {"include-group": "lint"}]}}
    assert missing_dev_tools(project, tomllib.loads(BASELINE)) == ["mypy>=1.18"]
    assert missing_dev_tools({}, tomllib.loads(BASELINE)) == ["ruff>=0.14", "mypy>=1.18"]
    assert missing_dev_tools({"dependency-groups": {"dev": ["MyPy", "ruff ; python_version > '3'"]}}, tomllib.loads(BASELINE)) == []


def test_backup_never_overwrites_an_earlier_backup(tmp_path: Path) -> None:
    original: Path = tmp_path / "a.txt"
    original.write_text("one", encoding="utf-8")
    assert backup(original) == tmp_path / "a.txt.orig"
    original.write_text("two", encoding="utf-8")
    assert backup(original) == tmp_path / "a.txt.orig.1"
    assert (tmp_path / "a.txt.orig").read_text(encoding="utf-8") == "one"
    assert (tmp_path / "a.txt.orig.1").read_text(encoding="utf-8") == "two"


# --------------------------------------------------------------------------- #
# main: which files are replaced under which flags
# --------------------------------------------------------------------------- #

NEW: str = "new\n"
OLD: str = "old\n"


class Repo:
    """A target repository, with the setup script's staged templates and history beside it."""

    def __init__(self, root: Path) -> None:
        """Make the repository and the stage directory under ``root``."""
        self.root: Path = root / "repo"
        self.stage: Path = root / "stage"
        self.hashes: Path = root / "hashes.json"
        self.root.mkdir()
        self.stage.mkdir()

    def template(self, path: str, text: str) -> None:
        """Stage a template, as the setup script would."""
        staged: Path = self.stage / path
        staged.parent.mkdir(parents=True, exist_ok=True)
        staged.write_text(text, encoding="utf-8", newline="")

    def existing(self, path: str, text: str) -> None:
        """Put a file in the repository before setup runs."""
        target: Path = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="")

    def read(self, path: str) -> str:
        """Return a repository file's text after setup ran."""
        return (self.root / path).read_text(encoding="utf-8")

    def run(self, *flags: str, answers: tuple[str, ...] = (), history: dict[str, object] | None = None) -> list[str]:
        """Run main with the given flags and answers; return the prompts it asked."""
        self.hashes.write_text(json.dumps(history or {"files": {}, "tables": {}}), encoding="utf-8")
        prompts: list[str] = []
        replies: list[str] = list(answers)

        def ask(prompt: str) -> str:
            prompts.append(prompt)
            if not replies:
                raise EOFError
            return replies.pop(0)

        assert main([str(self.stage), "--hashes", str(self.hashes), *flags], ask=ask) == 0
        return prompts


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Repo:
    made: Repo = Repo(tmp_path)
    monkeypatch.chdir(made.root)
    return made


def files_history(*paths: str) -> dict[str, object]:
    return {"files": {path: [digest(OLD)] for path in paths}, "tables": {}}


def test_missing_and_current_files_need_no_question(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    repo.template("tools/a.py", NEW)
    repo.template("b.txt", NEW)
    repo.existing("b.txt", NEW)
    assert repo.run() == []
    assert repo.read("tools/a.py") == NEW
    out: str = capsys.readouterr().out
    assert "  create   tools/a.py\n" in out
    assert "  current  b.txt\n" in out


@pytest.mark.parametrize(("answer", "expected"), [("y", NEW), ("yes", NEW), ("n", OLD), ("", OLD)])
def test_interactive_run_asks_before_replacing_an_unedited_older_version(repo: Repo, answer: str, expected: str) -> None:
    repo.template("a.txt", NEW)
    repo.existing("a.txt", OLD)
    prompts: list[str] = repo.run(answers=(answer,), history=files_history("a.txt"))
    assert prompts == ["Replace the 1 unedited item(s) above with the current version? [y/N] "]
    assert repo.read("a.txt") == expected
    assert not (repo.root / "a.txt.orig").exists()


def test_interactive_run_treats_end_of_input_as_no(repo: Repo) -> None:
    repo.template("a.txt", NEW)
    repo.existing("a.txt", OLD)
    repo.run(history=files_history("a.txt"))
    assert repo.read("a.txt") == OLD


def test_yes_alone_replaces_nothing_and_asks_nothing(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    repo.template("a.txt", NEW)
    repo.template("b.txt", NEW)
    repo.existing("a.txt", OLD)
    repo.existing("b.txt", "mine\n")
    assert repo.run("--yes", history=files_history("a.txt")) == []
    assert (repo.read("a.txt"), repo.read("b.txt")) == (OLD, "mine\n")
    out: str = capsys.readouterr().out
    assert "  outdated a.txt (unedited older version; --update replaces it)\n" in out
    assert "  edited   b.txt (--force replaces it)\n" in out


def test_yes_update_replaces_unedited_files_only(repo: Repo) -> None:
    repo.template("a.txt", NEW)
    repo.template("b.txt", NEW)
    repo.existing("a.txt", OLD)
    repo.existing("b.txt", "mine\n")
    assert repo.run("--yes", "--update", history=files_history("a.txt")) == []
    assert (repo.read("a.txt"), repo.read("b.txt")) == (NEW, "mine\n")


def test_interactive_force_asks_again_before_replacing_edited_files(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    repo.template("b.txt", NEW)
    repo.existing("b.txt", "mine\n")
    prompts: list[str] = repo.run("--force", answers=("y",))
    assert prompts == ["Replace the 1 EDITED item(s) above? Each file is saved as <name>.orig first. [y/N] "]
    assert repo.read("b.txt") == NEW
    assert repo.read("b.txt.orig") == "mine\n"
    assert "  backup   b.txt -> b.txt.orig\n" in capsys.readouterr().out


def test_interactive_force_declined_keeps_edited_files(repo: Repo) -> None:
    repo.template("b.txt", NEW)
    repo.existing("b.txt", "mine\n")
    repo.run("--force", answers=("n",))
    assert repo.read("b.txt") == "mine\n"
    assert not (repo.root / "b.txt.orig").exists()


def test_yes_force_replaces_everything_with_backups_and_asks_nothing(repo: Repo) -> None:
    repo.template("a.txt", NEW)
    repo.template("b.txt", NEW)
    repo.existing("a.txt", OLD)
    repo.existing("b.txt", "mine\n")
    assert repo.run("--yes", "--force", history=files_history("a.txt")) == []
    assert (repo.read("a.txt"), repo.read("b.txt"), repo.read("b.txt.orig")) == (NEW, NEW, "mine\n")
    assert not (repo.root / "a.txt.orig").exists()


def test_without_force_edited_files_are_reported_as_kept(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    repo.template("b.txt", NEW)
    repo.existing("b.txt", "mine\n")
    assert repo.run() == []
    assert "Kept 1 edited item(s). Re-run with --force to replace them" in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# main: pyproject.toml, table by table
# --------------------------------------------------------------------------- #


def tables_history(name: str, old: str) -> dict[str, object]:
    return {"files": {}, "tables": {f"tool.{name}": [table_digest(tomllib.loads(old)["tool"][name])]}}


def test_a_missing_pyproject_is_created_whole(repo: Repo) -> None:
    repo.template("pyproject.toml", BASELINE)
    repo.run()
    assert repo.read("pyproject.toml") == BASELINE


def test_pyproject_tables_are_compared_one_by_one(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    repo.template("pyproject.toml", BASELINE)
    old_ruff: str = '[tool.ruff]\nline-length = 100\n\n[tool.ruff.lint]\nselect = ["E"]\n'
    repo.existing("pyproject.toml", '[project]\nname = "mine"\n\n[dependency-groups]\ndev = ["ruff"]\n\n' + old_ruff)
    repo.run("--yes", history=tables_history("ruff", old_ruff))
    out: str = capsys.readouterr().out
    assert "  outdated pyproject.toml [tool.ruff] (unedited older version; --update replaces it)\n" in out
    assert "  missing  pyproject.toml [tool.mypy] (--update adds it)\n" in out
    assert "pyproject.toml [dependency-groups] dev lacks: mypy>=1.18\n" in out


def test_update_rewrites_unedited_tables_in_place(repo: Repo) -> None:
    repo.template("pyproject.toml", BASELINE)
    old_ruff: str = '[tool.ruff]\nline-length = 100\n\n[tool.ruff.lint]\nselect = ["E"]\n'
    repo.existing("pyproject.toml", '[project]\nname = "mine"\n\n' + old_ruff)
    repo.run("--yes", "--update", history=tables_history("ruff", old_ruff))
    assert repo.read("pyproject.toml") == '[project]\nname = "mine"\n\n' + BASELINE[BASELINE.index("[tool.ruff]") :]
    assert repo.read("pyproject.toml.orig") == '[project]\nname = "mine"\n\n' + old_ruff


def test_update_backs_up_comments_inside_an_unedited_table(repo: Repo) -> None:
    """Comments do not change a table's parsed value, so only the backup keeps one the user added."""
    repo.template("pyproject.toml", BASELINE)
    old_mypy: str = "[tool.mypy]\nstrict = false\n"
    commented: str = "[tool.mypy]\n# Keep this: reviewed by security.\nstrict = false\n"
    repo.existing("pyproject.toml", commented)
    repo.run("--yes", "--update", history=tables_history("mypy", old_mypy))
    assert repo.read("pyproject.toml.orig") == commented


def test_force_rewrites_edited_tables_after_a_backup(repo: Repo) -> None:
    repo.template("pyproject.toml", BASELINE)
    edited: str = '[project]\nname = "mine"\n\n[tool.ruff]\nline-length = 1\n\n[tool.mypy]\nstrict = true\n'
    repo.existing("pyproject.toml", edited)
    repo.run("--yes", "--force")
    assert tomllib.loads(repo.read("pyproject.toml"))["tool"]["ruff"] == tomllib.loads(BASELINE)["tool"]["ruff"]
    assert repo.read("pyproject.toml.orig") == edited


def test_a_pyproject_that_cannot_be_rewritten_is_left_alone(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    repo.template("pyproject.toml", BASELINE)
    repo.existing("pyproject.toml", "[tool]\nruff = { line-length = 1 }\nmypy = { strict = true }\n")
    repo.run("--yes", "--force")
    assert repo.read("pyproject.toml") == "[tool]\nruff = { line-length = 1 }\nmypy = { strict = true }\n"
    assert not (repo.root / "pyproject.toml.orig").exists()
    assert "pyproject.toml: could not rewrite [tool.ruff] in place; merge by hand\n" in capsys.readouterr().out


def test_runs_as_script(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Executed as a script, the module exits with ``main``'s status."""
    stage: Path = tmp_path / "stage"
    stage.mkdir()
    hashes: Path = tmp_path / "hashes.json"
    hashes.write_text('{"files": {}, "tables": {}}', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    script: Path = Path(__file__).parent.parent / "skill" / "tools" / "setup_files.py"
    monkeypatch.setattr(sys, "argv", [str(script), str(stage), "--hashes", str(hashes), "--yes"])
    exit_info: pytest.ExceptionInfo[SystemExit]
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_path(str(script), run_name="__main__")
    assert exit_info.value.code == 0


def test_a_kept_settings_file_gets_merge_advice(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    repo.template(".claude/settings.json", NEW)
    repo.existing(".claude/settings.json", "mine\n")
    repo.run("--yes")
    assert 'merge its "hooks" block by hand' in capsys.readouterr().out


def test_no_merge_advice_when_settings_are_current(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    repo.template(".claude/settings.json", NEW)
    repo.template("b.txt", NEW)
    repo.existing(".claude/settings.json", NEW)
    repo.existing("b.txt", "mine\n")
    repo.run("--yes")
    assert "hooks" not in capsys.readouterr().out


def test_declined_force_still_reports_what_was_kept(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    repo.template("b.txt", NEW)
    repo.existing("b.txt", "mine\n")
    repo.run("--force", answers=("n",))
    out: str = capsys.readouterr().out
    assert "\nKept 1 edited item(s).\n" in out


def test_backups_are_listed_for_review(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    repo.template("b.txt", NEW)
    repo.existing("b.txt", "mine\n")
    repo.run("--yes", "--force")
    assert "\nBacked up: b.txt.orig. Compare each with its file, then delete it; setup does not stage backups.\n" in capsys.readouterr().out


def test_no_backup_note_without_backups(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    repo.template("a.txt", NEW)
    repo.existing("a.txt", OLD)
    repo.run("--yes", "--update", history=files_history("a.txt"))
    assert "Backed up" not in capsys.readouterr().out


def test_help_documents_every_option(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["--help"])
    out: str = capsys.readouterr().out
    assert "\n- current: identical to the template" in out
    flat: str = " ".join(out.split())  # argparse wraps help text at the terminal width
    assert "Install the setup script's staged templates into a repository without silently losing edits." in flat
    assert "directory holding the templates, laid out as in the repository" in flat
    assert "JSON digests of every earlier template version" in flat
    assert "never ask; replace only what --update or --force allows" in flat
    assert "with --yes, replace unedited earlier versions" in flat
    assert "like --update, and also replace edited files and tables, saving <file>.orig first" in flat


def test_hashes_are_required(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_info: pytest.ExceptionInfo[SystemExit]
    with pytest.raises(SystemExit) as exit_info:
        main([str(tmp_path)])
    assert exit_info.value.code == 2
    assert "--hashes" in capsys.readouterr().err


def test_an_undecodable_file_counts_as_edited(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    repo.template("a.txt", NEW)
    (repo.root / "a.txt").write_bytes(b"\xff\xfe old\n")
    repo.run("--yes", "--update", history=files_history("a.txt"))
    assert (repo.root / "a.txt").read_bytes() == b"\xff\xfe old\n"
    assert "  edited   a.txt (--force replaces it)\n" in capsys.readouterr().out


def test_new_files_get_their_directories_and_a_write_line(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    repo.template("a/b/c.txt", NEW)
    repo.run()
    assert repo.read("a/b/c.txt") == NEW
    assert "  write    a/b/c.txt\n" in capsys.readouterr().out


def test_every_backup_is_listed(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    repo.template("a.txt", NEW)
    repo.template("b.txt", NEW)
    repo.existing("a.txt", "mine\n")
    repo.existing("b.txt", "mine\n")
    repo.run("--yes", "--force")
    assert "\nBacked up: a.txt.orig, b.txt.orig. Compare each" in capsys.readouterr().out


def test_backup_keeps_counting(tmp_path: Path) -> None:
    original: Path = tmp_path / "a.txt"
    original.write_text("one", encoding="utf-8")
    backup(original)
    backup(original)
    assert backup(original) == tmp_path / "a.txt.orig.2"


def test_every_table_that_cannot_be_rewritten_is_named(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    repo.template("pyproject.toml", BASELINE)
    repo.existing("pyproject.toml", "[tool]\nruff = { line-length = 1 }\nmypy = { strict = false }\n")
    repo.run("--yes", "--force")
    assert "pyproject.toml: could not rewrite [tool.ruff], [tool.mypy] in place; merge by hand\n" in capsys.readouterr().out


def test_a_pyproject_without_tool_tables_lacks_them_all(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    repo.template("pyproject.toml", BASELINE)
    repo.existing("pyproject.toml", '[project]\nname = "mine"\n')
    repo.run("--yes")
    out: str = capsys.readouterr().out
    assert "  missing  pyproject.toml [tool.ruff] (--update adds it)\n" in out
    assert "  missing  pyproject.toml [tool.mypy] (--update adds it)\n" in out
    assert "pyproject.toml [dependency-groups] dev lacks: ruff>=0.14, mypy>=1.18\nAdd them with 'uv add --dev', or copy them from the baseline.\n" in out


def test_no_dev_tool_report_without_a_staged_pyproject(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    repo.existing("pyproject.toml", '[project]\nname = "mine"\n')
    repo.run("--yes")
    assert "dev lacks" not in capsys.readouterr().out


def test_rewrite_appends_several_missing_tables_one_blank_line_apart() -> None:
    result: str = rewrite_tables('[project]\nname = "mine"\n', BASELINE, {"ruff", "mypy"})
    assert result == '[project]\nname = "mine"\n\n' + BASELINE[BASELINE.index("[tool.ruff]") :]


def test_rewrite_recognizes_headers_written_with_spaces() -> None:
    result: str = rewrite_tables("[ tool.mypy ]\nstrict = false\n", BASELINE, {"mypy"})
    assert result == "[tool.mypy]\nstrict = true\n"


def test_requirement_names_ignore_separator_style() -> None:
    project: dict[str, object] = {"dependency-groups": {"dev": ["my.tool", "Other_Tool"]}}
    baseline: dict[str, object] = {"dependency-groups": {"dev": ["my_tool>=1", "other-tool"]}}
    assert missing_dev_tools(project, baseline) == []


def test_help_lists_the_options_exactly(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["--help"])
    flat: str = " ".join(capsys.readouterr().out.split())
    assert flat.endswith(
        "positional arguments: stage directory holding the templates, laid out as in the repository"
        " options: -h, --help show this help message and exit"
        " --hashes HASHES JSON digests of every earlier template version"
        " --yes never ask; replace only what --update or --force allows"
        " --update with --yes, replace unedited earlier versions"
        " --force like --update, and also replace edited files and tables, saving <file>.orig first"
    )


@pytest.mark.parametrize("last", ["# owned by X\n", "# trailing spaces  \n"], ids=["ends-in-x", "ends-in-spaces"])
def test_rewrite_keeps_the_last_line_exactly(last: str) -> None:
    project: str = "[tool.mypy]\nstrict = false\n\n[tool.black]\n" + last
    assert rewrite_tables(project, BASELINE, {"mypy"}) == "[tool.mypy]\nstrict = true\n\n[tool.black]\n" + last


def test_rewrite_keeps_the_comment_above_the_next_section() -> None:
    project: str = '[tool.mypy]\nstrict = false\n\n# The project itself.\n\n[project]\nname = "x"\n'
    assert rewrite_tables(project, BASELINE, {"mypy"}) == '[tool.mypy]\nstrict = true\n\n# The project itself.\n\n[project]\nname = "x"\n'


def test_rewrite_replaces_the_comment_above_a_replaced_table() -> None:
    project: str = '[project]\nname = "x"\n\n# Old mypy settings.\n[tool.mypy]\nstrict = false\n'
    assert rewrite_tables(project, BASELINE, {"mypy"}) == '[project]\nname = "x"\n\n[tool.mypy]\nstrict = true\n'


def test_missing_dev_tools_follows_included_groups() -> None:
    project: dict[str, object] = {
        "dependency-groups": {
            "dev": [{"include-group": "checks"}],
            "checks": ["ruff", {"include-group": "types"}],
            "types": ["mypy", {"include-group": "checks"}, 1],
        },
    }
    assert missing_dev_tools(project, tomllib.loads(BASELINE)) == []


def test_rewrite_takes_a_comment_on_the_first_line_with_its_table() -> None:
    assert rewrite_tables("# Old mypy settings.\n[tool.mypy]\nstrict = false\n", BASELINE, {"mypy"}) == "[tool.mypy]\nstrict = true\n"


def test_rewrite_recognizes_an_indented_comment() -> None:
    project: str = '[tool.mypy]\nstrict = false\n\n  # The project itself.\n[project]\nname = "x"\n'
    assert rewrite_tables(project, BASELINE, {"mypy"}) == '[tool.mypy]\nstrict = true\n\n  # The project itself.\n[project]\nname = "x"\n'
