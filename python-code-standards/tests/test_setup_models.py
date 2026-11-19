"""Tests for asking which models to use and recording the answers under ``~/.claude``."""

from __future__ import annotations

import ast
import json
import re
import runpy
import sys
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from unittest.mock import Mock

import pytest

from skill.tools import setup_models
from skill.tools.setup_models import (
    CLAUDE_CODE,
    COPILOT,
    DEFAULTS,
    END,
    HOSTS,
    START,
    Host,
    InvalidBlock,
    ModelChoices,
    ask_choices,
    ask_hosts,
    detected_hosts,
    main,
    merge_block,
    merge_model,
    render_block,
    selected_hosts,
    stored_choices,
)

CHOSEN: ModelChoices = ModelChoices(coordinator="opus", coding="haiku", reviewer_provider="claude", reviewer_model="sonnet")

INVALID_LAYOUTS: list[tuple[str, str]] = [
    (f"intro\n{START}\nuser text kept\n", f"{START} has no {END} after it"),
    (f"intro\n{END}\nuser text kept\n", f"{END} has no {START} before it"),
    (f"{END}\nuser text\n{START}\n", f"{END} comes before {START}"),
    (f"{START}\na\n{END}\n{START}\nb\n{END}\n", "2 start and 2 end markers; it may hold one models block only"),
    (f"{START}\n{START}\n{END}\n", "2 start and 1 end markers; it may hold one models block only"),
    (f"{START}\n{END}\n{END}\n", "1 start and 2 end markers; it may hold one models block only"),
]
"""Each invalid marker layout of ``CLAUDE.md``, with the problem setup names."""
INVALID_IDS: list[str] = ["orphan-start", "orphan-end", "end-before-start", "two-blocks", "repeated-start", "repeated-end"]


def replies(*answers: str) -> Callable[[str], str]:
    """Return a fake ``input`` giving each answer in turn, then raising ``EOFError`` as a closed stdin does."""
    queue: Iterator[str] = iter(answers)

    def ask(_question: str) -> str:
        try:
            return next(queue)
        except StopIteration:
            raise EOFError from None

    return ask


def test_render_block_is_delimited_by_the_markers() -> None:
    block: str = render_block(CHOSEN)
    assert block.startswith(START + "\n")
    assert block.endswith("\n" + END)
    assert "`haiku`" in block
    assert "`claude`" in block


def test_stored_choices_read_back_what_render_block_wrote() -> None:
    assert stored_choices(f"# Mine\n\n{render_block(CHOSEN)}\n\nmore\n") == CHOSEN


def test_defaults_are_sonnet_coordinating_and_opus_coding() -> None:
    assert ModelChoices(coordinator="sonnet", coding="opus", reviewer_provider="codex", reviewer_model="gpt-5.4") == DEFAULTS


def test_stored_choices_are_none_without_a_block() -> None:
    assert stored_choices("# Mine\n") is None


@pytest.mark.parametrize(("text", "reason"), INVALID_LAYOUTS, ids=INVALID_IDS)
def test_stored_choices_report_an_invalid_marker_layout(text: str, reason: str) -> None:
    assert stored_choices(text) == InvalidBlock(reason)


@pytest.mark.parametrize(("text", "reason"), INVALID_LAYOUTS, ids=INVALID_IDS)
def test_merge_block_refuses_an_invalid_marker_layout(text: str, reason: str) -> None:
    with pytest.raises(ValueError, match=re.escape(reason)):
        merge_block(text, "BLOCK")


def test_stored_choices_fill_a_missing_line_with_its_default() -> None:
    block: str = "\n".join(line for line in render_block(CHOSEN).splitlines() if "Coding" not in line)
    assert stored_choices(block) == ModelChoices(coordinator="opus", coding=DEFAULTS.coding, reviewer_provider="claude", reviewer_model="sonnet")


def test_merge_block_appends_when_absent_and_keeps_the_text_byte_identical() -> None:
    text: str = "# Rules\r\n\r\nkeep me\r\n"
    assert merge_block(text, "BLOCK") == text + "\nBLOCK\n"


@pytest.mark.parametrize(("text", "expected"), [("", "BLOCK\n"), ("no newline", "no newline\n\nBLOCK\n")], ids=["empty", "unterminated"])
def test_merge_block_separates_an_appended_block(text: str, expected: str) -> None:
    assert merge_block(text, "BLOCK") == expected


def test_merge_block_replaces_only_between_the_markers() -> None:
    text: str = f"before\r\n{START}\nold\n{END}\r\nafter\n"
    assert merge_block(text, "BLOCK") == "before\r\nBLOCK\r\nafter\n"


def test_merge_model_adds_a_missing_model_and_keeps_other_keys() -> None:
    assert merge_model({"hooks": {}, "env": {"A": "1"}}, "opus", overwrite=False) == {"hooks": {}, "env": {"A": "1"}, "model": "opus"}


@pytest.mark.parametrize(("overwrite", "expected"), [(False, "sonnet"), (True, "opus")], ids=["kept", "overwritten"])
def test_merge_model_replaces_an_existing_model_only_when_told_to(*, overwrite: bool, expected: str) -> None:
    assert merge_model({"model": "sonnet", "x": 1}, "opus", overwrite=overwrite) == {"model": expected, "x": 1}


def test_ask_choices_takes_each_default_on_an_empty_reply_or_closed_stdin() -> None:
    assert ask_choices(CHOSEN, replies("", "")) == CHOSEN


def test_ask_choices_records_free_text_answers() -> None:
    assert ask_choices(DEFAULTS, replies("my-coordinator", "my-coder", "Claude", "")) == ModelChoices("my-coordinator", "my-coder", "claude", "opus")


def test_ask_choices_keeps_the_stored_model_while_the_provider_is_unchanged() -> None:
    assert ask_choices(CHOSEN, replies("", "", "claude", "")) == CHOSEN


def test_ask_choices_asks_the_provider_again_until_it_is_known(capsys: pytest.CaptureFixture[str]) -> None:
    assert ask_choices(DEFAULTS, replies("", "", "gemini", "codex", "gpt-5.4-mini")).reviewer_model == "gpt-5.4-mini"
    assert "Answer codex or claude." in capsys.readouterr().out


@dataclass(frozen=True)
class Home:
    """A temporary home directory and the ``main`` call that uses it."""

    root: Path

    @property
    def claude(self) -> Path:
        """Return the ``.claude`` directory setup writes into."""
        return self.root / ".claude"

    def run(self, *argv: str, answers: tuple[str, ...] = (), links: Mapping[str, Path] | None = None) -> int:
        """Run ``main`` against this home with the given replies.

        ``links`` maps a file name under ``.claude`` to where it resolves, standing in for a
        symbolic link, which Windows creates only with privilege; every other path resolves to itself.
        """
        targets: dict[Path, Path] = {self.claude / name: target for name, target in (links or {}).items()}
        return main([*argv, "--repo", str(self.root / "repo")], ask=replies(*answers), home=lambda: self.root, resolve=lambda path: targets.get(path, path), environ={})

    def memory(self) -> str:
        """Return ``CLAUDE.md`` exactly as stored."""
        return (self.claude / "CLAUDE.md").read_text(encoding="utf-8", newline="")

    def settings(self) -> dict[str, object]:
        """Return ``settings.json`` parsed."""
        parsed: dict[str, object] = json.loads((self.claude / "settings.json").read_text(encoding="utf-8"))
        return parsed


@pytest.fixture
def home(tmp_path: Path) -> Home:
    """A home directory that exists, as a real one does, with no ``.claude`` yet."""
    root: Path = tmp_path / "home"
    root.mkdir()
    return Home(root)


def test_yes_writes_the_defaults_on_a_first_run(home: Home, capsys: pytest.CaptureFixture[str]) -> None:
    assert home.run("--yes") == 0
    assert stored_choices(home.memory()) == DEFAULTS
    assert home.settings() == {"model": "sonnet"}
    out: str = capsys.readouterr().out
    assert str(home.claude / "CLAUDE.md") in out
    assert f'"model": "{DEFAULTS.coordinator}"' in out


def test_yes_keeps_an_existing_block_and_a_recorded_model(home: Home, capsys: pytest.CaptureFixture[str]) -> None:
    home.claude.mkdir()
    (home.claude / "CLAUDE.md").write_text(render_block(CHOSEN) + "\n", encoding="utf-8", newline="")
    (home.claude / "settings.json").write_text('{"model": "haiku"}', encoding="utf-8", newline="")
    assert home.run("--yes") == 0
    assert home.memory() == render_block(CHOSEN) + "\n"
    assert home.settings() == {"model": "haiku"}
    assert "Kept the models" in capsys.readouterr().out


def test_yes_with_an_existing_block_still_records_a_missing_settings_model(home: Home) -> None:
    """An interrupted run or a lost ``model`` key is repaired from the stored coordinator, leaving the block alone."""
    home.claude.mkdir()
    hand_edited: str = render_block(CHOSEN).replace("## Models", "## My models") + "\n"
    (home.claude / "CLAUDE.md").write_text(hand_edited, encoding="utf-8", newline="")
    assert home.run("--yes") == 0
    assert home.memory() == hand_edited
    assert home.settings() == {"model": CHOSEN.coordinator}


def test_yes_never_overwrites_an_existing_settings_model(home: Home, capsys: pytest.CaptureFixture[str]) -> None:
    home.claude.mkdir()
    (home.claude / "settings.json").write_text('{"model": "haiku", "hooks": {}}', encoding="utf-8", newline="")
    assert home.run("--yes") == 0
    assert home.settings() == {"model": "haiku", "hooks": {}}
    assert stored_choices(home.memory()) == DEFAULTS
    assert 'keeps "model": "haiku"' in capsys.readouterr().out


def test_an_interactive_first_run_writes_after_confirmation(home: Home) -> None:
    assert home.run(answers=("", "sonnet", "haiku", "claude", "opus", "y")) == 0
    assert stored_choices(home.memory()) == ModelChoices("sonnet", "haiku", "claude", "opus")
    assert home.settings() == {"model": "sonnet"}


@pytest.mark.parametrize("answers", [("", "", "", "", "", "n"), ()], ids=["no", "closed-stdin"])
def test_an_interactive_run_writes_nothing_unconfirmed(home: Home, capsys: pytest.CaptureFixture[str], answers: tuple[str, ...]) -> None:
    assert home.run(answers=answers) == 0
    assert not home.claude.exists()
    assert "Not written" in capsys.readouterr().out


def test_an_interactive_rerun_offers_the_stored_values_and_changes_nothing_when_kept(home: Home, capsys: pytest.CaptureFixture[str]) -> None:
    home.claude.mkdir()
    (home.claude / "CLAUDE.md").write_text("mine\n\n" + render_block(CHOSEN) + "\n", encoding="utf-8", newline="")
    (home.claude / "settings.json").write_text('{"model": "opus"}', encoding="utf-8", newline="")
    assert home.run() == 0
    assert home.memory() == "mine\n\n" + render_block(CHOSEN) + "\n"
    assert "nothing to change" in capsys.readouterr().out


def test_an_interactive_rerun_with_a_new_coordinator_overwrites_the_settings_model(home: Home) -> None:
    home.claude.mkdir()
    (home.claude / "CLAUDE.md").write_text("mine\n\n" + render_block(CHOSEN) + "\ntail\n", encoding="utf-8", newline="")
    (home.claude / "settings.json").write_text('{"model": "opus", "hooks": {}}', encoding="utf-8", newline="")
    assert home.run(answers=("", "sonnet", "", "", "", "y")) == 0
    assert home.memory() == "mine\n\n" + render_block(ModelChoices("sonnet", "haiku", "claude", "sonnet")) + "\ntail\n"
    assert home.settings() == {"model": "sonnet", "hooks": {}}


@pytest.mark.parametrize("argv", [("--yes",), ()], ids=["yes", "interactive"])
@pytest.mark.parametrize("layout", INVALID_LAYOUTS, ids=INVALID_IDS)
def test_an_invalid_marker_layout_writes_nothing_and_fails(home: Home, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, layout: tuple[str, str], argv: tuple[str, ...]) -> None:
    """Regression: an orphan START once made the second run's merge span, and delete, the user's text."""
    text: str
    reason: str
    text, reason = layout
    home.claude.mkdir()
    (home.claude / "CLAUDE.md").write_bytes(text.encode())
    merge: Mock = Mock(side_effect=AssertionError)
    monkeypatch.setattr(setup_models, "merge_block", merge)
    assert home.run(*argv, answers=("", "", "", "", "", "y")) == 1
    assert (home.claude / "CLAUDE.md").read_bytes() == text.encode()
    assert not (home.claude / "settings.json").exists()
    err: str = capsys.readouterr().err
    assert str(home.claude / "CLAUDE.md") in err
    assert reason in err
    merge.assert_not_called()


def test_yes_skips_a_claude_md_linked_outside_home_and_fails(home: Home, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo_file: Path = tmp_path / "repo" / "CLAUDE.md"
    assert home.run("--yes", links={"CLAUDE.md": repo_file}) == 1
    assert not (home.claude / "CLAUDE.md").exists()
    assert home.settings() == {"model": "sonnet"}
    err: str = capsys.readouterr().err
    assert f"{home.claude / 'CLAUDE.md'} is a link to {repo_file}" in err


def test_yes_skips_a_settings_file_linked_outside_home_and_fails(home: Home, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo_file: Path = tmp_path / "repo" / "settings.json"
    assert home.run("--yes", links={"settings.json": repo_file}) == 1
    assert not (home.claude / "settings.json").exists()
    assert stored_choices(home.memory()) == DEFAULTS
    assert f"{home.claude / 'settings.json'} is a link to {repo_file}" in capsys.readouterr().err


def test_yes_with_a_kept_block_does_not_fail_on_a_link_it_would_not_write(home: Home, tmp_path: Path) -> None:
    home.claude.mkdir()
    (home.claude / "CLAUDE.md").write_text(render_block(CHOSEN) + "\n", encoding="utf-8", newline="")
    assert home.run("--yes", links={"CLAUDE.md": tmp_path / "repo" / "CLAUDE.md"}) == 0
    assert home.settings() == {"model": CHOSEN.coordinator}


def test_yes_with_a_kept_block_skips_a_settings_repair_through_an_outside_link(home: Home, tmp_path: Path) -> None:
    home.claude.mkdir()
    (home.claude / "CLAUDE.md").write_text(render_block(CHOSEN) + "\n", encoding="utf-8", newline="")
    assert home.run("--yes", links={"settings.json": tmp_path / "repo" / "settings.json"}) == 1
    assert not (home.claude / "settings.json").exists()


def test_a_link_inside_home_is_written_without_asking(home: Home) -> None:
    assert home.run("--yes", links={"CLAUDE.md": home.root / "dotfiles" / "CLAUDE.md"}) == 0
    assert stored_choices(home.memory()) == DEFAULTS


def test_an_interactive_run_writes_through_an_outside_link_only_after_its_own_yes(home: Home, tmp_path: Path) -> None:
    repo_file: Path = tmp_path / "repo" / "CLAUDE.md"
    questions: list[str] = []
    answer_next: Callable[[str], str] = replies("", "", "", "", "", "y", "y")

    def ask(question: str) -> str:
        questions.append(question)
        return answer_next(question)

    assert main([], ask=ask, home=lambda: home.root, resolve=lambda path: repo_file if path == home.claude / "CLAUDE.md" else path, environ={}) == 0
    assert stored_choices(home.memory()) == DEFAULTS
    assert home.settings() == {"model": "sonnet"}
    assert questions[5].endswith(f"Write through the link to {repo_file}? [y/N] ")
    assert questions[6] == "\nWrite the changes above? [y/N] "


@pytest.mark.parametrize("answers", [("", "", "", "", "", "n", "y"), ("", "", "", "", "")], ids=["no", "closed-stdin"])
def test_an_interactive_run_declining_a_link_skips_only_that_file(home: Home, tmp_path: Path, capsys: pytest.CaptureFixture[str], answers: tuple[str, ...]) -> None:
    assert home.run(answers=answers, links={"CLAUDE.md": tmp_path / "repo" / "CLAUDE.md"}) == 0
    assert not (home.claude / "CLAUDE.md").exists()
    assert f"skip     {home.claude / 'CLAUDE.md'}" in capsys.readouterr().out


def test_runs_as_script(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Executed as a script, the module exits with ``main``'s status and writes under ``Path.home()``."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("COPILOT_HOME", raising=False)
    script: Path = Path(__file__).parent.parent / "skill" / "tools" / "setup_models.py"
    monkeypatch.setattr(sys, "argv", [str(script), "--yes"])
    exit_info: pytest.ExceptionInfo[SystemExit]
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_path(str(script), run_name="__main__")
    assert exit_info.value.code == 0
    assert (tmp_path / ".claude" / "CLAUDE.md").is_file()


CLAUDE_GUARD: str = "Other agents' instruction files (`AGENTS.md`, `.github/copilot-instructions.md`) are not for you; do not open them unless a change touches them."
COPILOT_GUARD: str = "Other agents' instruction files (`CLAUDE.md`, `.claude/`, `AGENTS.md`) are not for you; do not open them unless a change touches them."

OLD_COPILOT_BLOCK: str = """<!-- python-code-standards:models -->
## Models (Copilot)

- Coordinator model (main session default; runs the tests): `Claude Sonnet 5.5`
- Coding model (agents that write code): `Claude Opus 5.5`
- Adversarial code-review provider: `copilot`
- Adversarial code-review model: `GPT-6 Astra`
<!-- /python-code-standards:models -->"""
"""Copilot's defaults as setup wrote them before the coder guard."""

COPILOT_BLOCK: str = OLD_COPILOT_BLOCK.replace("\n<!-- /", f"\n\n{COPILOT_GUARD}\n<!-- /")
"""Copilot's defaults as setup writes them now, the coder guard last."""

CHECKLIST: tuple[str, ...] = (
    "VS Code agent mode: open a session, ask which models it was told to use, confirm each hook fires.",
    "Copilot CLI: open a session, ask which models it was told to use, confirm each hook fires.",
)


def test_hosts_are_claude_code_then_copilot() -> None:
    assert [host.name for host in HOSTS] == ["claude-code", "copilot"]
    assert CLAUDE_CODE.defaults == DEFAULTS
    assert (CLAUDE_CODE.home_dir, CLAUDE_CODE.home_env, CLAUDE_CODE.instructions_name, CLAUDE_CODE.settings_model_key) == (".claude", None, "CLAUDE.md", "model")
    assert (COPILOT.home_dir, COPILOT.home_env, COPILOT.instructions_name, COPILOT.settings_model_key) == (".copilot", "COPILOT_HOME", "copilot-instructions.md", None)
    assert COPILOT.defaults == ModelChoices("Claude Sonnet 5.5", "Claude Opus 5.5", "copilot", "GPT-6 Astra")
    assert COPILOT.providers == ("copilot", "none")
    assert CLAUDE_CODE.providers == ("codex", "claude")


def test_copilot_block_holds_roles_and_model_names_only() -> None:
    """NFR-09: the rendered block equals the documented one, so it carries nothing personal."""
    assert render_block(COPILOT.defaults, COPILOT) == COPILOT_BLOCK


@pytest.mark.parametrize(("host", "guard"), [(CLAUDE_CODE, CLAUDE_GUARD), (COPILOT, COPILOT_GUARD)], ids=["claude-code", "copilot"])
def test_each_coding_host_block_ends_with_its_coder_guard(host: Host, guard: str) -> None:
    assert render_block(host.defaults, host).endswith(f"\n\n{guard}\n{END}")


def test_a_block_written_before_the_guard_still_reads_back() -> None:
    assert stored_choices(OLD_COPILOT_BLOCK, COPILOT) == COPILOT.defaults


@pytest.mark.parametrize("host", HOSTS, ids=[host.name for host in HOSTS])
def test_a_block_and_its_guard_stay_under_100_words(host: Host) -> None:
    """NFR-12: always-on text stays small."""
    assert len(render_block(host.defaults, host).split()) < 100


def test_a_missing_copilot_line_takes_the_copilot_default() -> None:
    block: str = "\n".join(line for line in render_block(CHOSEN, COPILOT).splitlines() if "Coding" not in line)
    assert stored_choices(block, COPILOT) == ModelChoices("opus", "Claude Opus 5.5", "claude", "sonnet")


def test_the_module_imports_no_network_module() -> None:
    """NFR-09: the tool makes no network call, so it imports nothing that could."""
    tree: ast.Module = ast.parse(Path(setup_models.__file__).read_text(encoding="utf-8"))
    imported: set[str] = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imported |= {(node.module or "").split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert imported.isdisjoint({"socket", "ssl", "http", "urllib", "ftplib", "smtplib", "requests", "httpx", "asyncio", "subprocess"})


@pytest.mark.parametrize(
    ("folders", "environ", "expected"),
    [
        ((), {}, ()),
        ((".claude",), {}, ("claude-code",)),
        ((".copilot",), {}, ("copilot",)),
        ((".claude", ".copilot"), {}, ("claude-code", "copilot")),
        (("elsewhere",), {"COPILOT_HOME": "elsewhere"}, ("copilot",)),
        ((), {"COPILOT_HOME": "missing"}, ()),
        ((".copilot",), {"COPILOT_HOME": "missing"}, ("copilot",)),
    ],
    ids=["none", "claude", "copilot", "both", "copilot-home", "copilot-home-missing", "copilot-home-missing-but-default-exists"],
)
def test_detected_hosts_are_those_whose_home_directory_exists(tmp_path: Path, folders: tuple[str, ...], environ: dict[str, str], expected: tuple[str, ...]) -> None:
    folder: str
    for folder in folders:
        (tmp_path / folder).mkdir()
    absolute: dict[str, str] = {key: str(tmp_path / value) for key, value in environ.items()}
    assert tuple(host.name for host in detected_hosts(tmp_path, absolute)) == expected


def test_a_copilot_file_is_not_a_detected_home(tmp_path: Path) -> None:
    (tmp_path / ".copilot").write_text("not a directory", encoding="utf-8")
    assert detected_hosts(tmp_path, {}) == ()


@pytest.mark.parametrize(
    ("configured", "detected", "expected"),
    [((COPILOT,), (CLAUDE_CODE, COPILOT), (COPILOT,)), ((), (COPILOT,), (COPILOT,)), ((), (), (CLAUDE_CODE,))],
    ids=["configured", "detected", "fallback"],
)
def test_selected_hosts_prefer_configured_then_detected_then_claude_code(configured: tuple[Host, ...], detected: tuple[Host, ...], expected: tuple[Host, ...]) -> None:
    assert selected_hosts(configured, detected) == expected


@pytest.mark.parametrize("answers", [("",), (), (" , ",)], ids=["empty", "closed-stdin", "separators-only"])
def test_ask_hosts_takes_the_default_without_an_answer(answers: tuple[str, ...]) -> None:
    assert ask_hosts((COPILOT,), replies(*answers)) == (COPILOT,)


def test_ask_hosts_asks_again_until_every_name_is_known(capsys: pytest.CaptureFixture[str]) -> None:
    assert ask_hosts((CLAUDE_CODE,), replies("copilot, gemini", "copilot claude-code")) == (CLAUDE_CODE, COPILOT)
    assert "Unknown host gemini; answer one or more of claude-code, copilot." in capsys.readouterr().out


def test_ask_choices_for_copilot_accepts_picker_and_its_own_providers(capsys: pytest.CaptureFixture[str]) -> None:
    assert ask_choices(COPILOT.defaults, replies("picker", "", "codex", "none", ""), COPILOT) == ModelChoices("picker", "Claude Opus 5.5", "none", "none")
    assert "Answer copilot or none." in capsys.readouterr().out


def test_ask_choices_for_copilot_offers_its_default_reviewer_after_a_provider_change() -> None:
    stored: ModelChoices = replace(COPILOT.defaults, reviewer_provider="none", reviewer_model="none")
    assert ask_choices(stored, replies("", "", "copilot", ""), COPILOT) == COPILOT.defaults


@dataclass(frozen=True)
class Machine:
    """A temporary home holding both hosts' directories, an injected environment, and a repository directory."""

    root: Path
    repo: Path
    environ: dict[str, str]

    @property
    def claude_md(self) -> Path:
        """Return Claude Code's instruction file."""
        return self.root / ".claude" / "CLAUDE.md"

    @property
    def copilot_md(self) -> Path:
        """Return Copilot's instruction file, under ``COPILOT_HOME`` when the environment sets it."""
        folder: str | None = self.environ.get("COPILOT_HOME")
        return (Path(folder) if folder else self.root / ".copilot") / "copilot-instructions.md"

    @property
    def agents_md(self) -> Path:
        """Return Codex's instruction file, under ``CODEX_HOME`` when the environment sets it."""
        folder: str | None = self.environ.get("CODEX_HOME")
        return (Path(folder) if folder else self.root / ".codex") / "AGENTS.md"

    def run(self, *argv: str, answers: tuple[str, ...] = (), resolve: Callable[[Path], Path] | None = None) -> int:
        """Run ``main`` against this machine; every path resolves to itself unless ``resolve`` says otherwise."""
        return main([*argv, "--repo", str(self.repo)], ask=replies(*answers), home=lambda: self.root, resolve=resolve or (lambda path: path), environ=self.environ)


@pytest.fixture
def machine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Machine:
    """A home with both host directories, run from inside a repository directory holding one file."""
    root: Path = tmp_path / "home"
    (root / ".claude").mkdir(parents=True)
    (root / ".copilot").mkdir()
    repo: Path = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("repo\n", encoding="utf-8")
    monkeypatch.chdir(repo)
    return Machine(root, repo, {})


def tree(folder: Path) -> dict[str, bytes]:
    """Return every file under ``folder`` with its bytes."""
    return {str(path.relative_to(folder)): path.read_bytes() for path in sorted(folder.rglob("*")) if path.is_file()}


def test_yes_configures_every_detected_host_and_writes_nothing_in_the_repo(machine: Machine, capsys: pytest.CaptureFixture[str]) -> None:
    """NFR-01: run from inside a repository, setup writes only under the home directory."""
    before: dict[str, bytes] = tree(machine.repo)
    assert machine.run("--yes") == 0
    assert tree(machine.repo) == before
    assert stored_choices(machine.claude_md.read_text(encoding="utf-8"), CLAUDE_CODE) == CLAUDE_CODE.defaults
    assert machine.copilot_md.read_text(encoding="utf-8") == COPILOT_BLOCK + "\n"
    assert sorted(path.name for path in machine.copilot_md.parent.iterdir()) == ["copilot-instructions.md"]
    out: str = capsys.readouterr().out
    assert "claude-code: written" in out
    assert "copilot: written" in out
    assert "Configured, not verified." in out
    assert "Stop gate configured for Claude Code only." in out
    assert "Copilot's mapping of the repo's `.claude/settings.json` hooks is unverified and Copilot already reads that file." in out
    assert "To check by hand run the gates in `docs/quality-gates.md`." in out
    assert "Pick the model in the picker or with `--model`" in out
    row: str
    for row in CHECKLIST:
        assert f"- [ ] {row}" in out


def test_yes_configures_copilot_alone_when_only_its_home_exists(tmp_path: Path) -> None:
    root: Path = tmp_path / "home"
    (root / ".copilot").mkdir(parents=True)
    assert main(["--yes"], ask=replies(), home=lambda: root, resolve=lambda path: path, environ={}) == 0
    assert (root / ".copilot" / "copilot-instructions.md").read_text(encoding="utf-8") == COPILOT_BLOCK + "\n"
    assert not (root / ".claude").exists()


def test_yes_keeps_configured_hosts_only(machine: Machine, capsys: pytest.CaptureFixture[str]) -> None:
    machine.copilot_md.write_text(COPILOT_BLOCK + "\n", encoding="utf-8", newline="")
    assert machine.run("--yes") == 0
    assert not machine.claude_md.exists()
    out: str = capsys.readouterr().out
    assert f"Kept the models in {machine.copilot_md}" in out
    assert "copilot: nothing to change" in out


def test_an_interactive_run_asks_each_selected_host_and_confirms_once(machine: Machine) -> None:
    questions: list[str] = []
    answer_next: Callable[[str], str] = replies("claude-code copilot", "", "", "", "", "picker", "", "none", "", "y")

    def ask(question: str) -> str:
        questions.append(question)
        return answer_next(question)

    assert main([], ask=ask, home=lambda: machine.root, resolve=lambda path: path, environ={}) == 0
    assert stored_choices(machine.claude_md.read_text(encoding="utf-8"), CLAUDE_CODE) == DEFAULTS
    assert stored_choices(machine.copilot_md.read_text(encoding="utf-8"), COPILOT) == ModelChoices("picker", "Claude Opus 5.5", "none", "none")
    assert questions[0] == "Hosts to configure (claude-code, copilot) [claude-code, copilot]: "
    assert [question for question in questions if "Write" in question] == ["\nWrite the changes above? [y/N] "]


def test_declining_writes_no_host(machine: Machine, capsys: pytest.CaptureFixture[str]) -> None:
    assert machine.run(answers=("", "", "", "", "", "", "", "", "", "n")) == 0
    assert not machine.claude_md.exists()
    assert not machine.copilot_md.exists()
    out: str = capsys.readouterr().out
    assert "claude-code: not written (declined)" in out
    assert "copilot: not written (declined)" in out


def test_copilot_text_outside_the_block_stays_byte_identical(machine: Machine) -> None:
    """NFR-02: CRLF and a missing final newline are kept; a block is appended, then replaced in place."""
    machine.copilot_md.write_bytes(b"# Mine\r\nno final newline")
    assert machine.run(answers=("copilot", "", "", "", "", "y")) == 0
    assert machine.copilot_md.read_bytes() == b"# Mine\r\nno final newline\n\n" + COPILOT_BLOCK.encode() + b"\n"
    machine.copilot_md.write_bytes(b"# Mine\r\n" + COPILOT_BLOCK.encode() + b"\r\ntail")
    assert machine.run(answers=("copilot", "Claude Haiku 5.5", "", "", "", "y")) == 0
    assert machine.copilot_md.read_bytes() == b"# Mine\r\n" + COPILOT_BLOCK.replace("Claude Sonnet 5.5", "Claude Haiku 5.5").encode() + b"\r\ntail"


@pytest.mark.parametrize("layout", INVALID_LAYOUTS, ids=INVALID_IDS)
def test_an_invalid_copilot_file_is_skipped_and_the_other_host_written(machine: Machine, capsys: pytest.CaptureFixture[str], layout: tuple[str, str]) -> None:
    """NFR-03 for the Copilot file: nothing written to it, the file named, the run failed."""
    text: str
    reason: str
    text, reason = layout
    machine.copilot_md.write_bytes(text.encode())
    assert machine.run("--yes") == 1
    assert machine.copilot_md.read_bytes() == text.encode()
    assert stored_choices(machine.claude_md.read_text(encoding="utf-8")) == DEFAULTS
    out: str
    err: str
    out, err = capsys.readouterr()
    assert f"{machine.copilot_md}: {reason}" in err
    assert "copilot: skipped (invalid)" in out


def test_an_unreadable_instruction_file_makes_its_host_invalid(machine: Machine, capsys: pytest.CaptureFixture[str]) -> None:
    machine.claude_md.write_bytes(b"\xff\xfe not utf-8")
    assert machine.run("--yes") == 1
    assert machine.claude_md.read_bytes() == b"\xff\xfe not utf-8"
    assert f"{machine.claude_md}: cannot be read" in capsys.readouterr().err
    assert machine.copilot_md.is_file()


@pytest.mark.parametrize(("content", "reason"), [("{not json", "cannot be parsed"), ("[]", "is not a JSON object")], ids=["unparsable", "not-an-object"])
def test_a_bad_settings_file_makes_claude_code_invalid(machine: Machine, capsys: pytest.CaptureFixture[str], content: str, reason: str) -> None:
    settings: Path = machine.root / ".claude" / "settings.json"
    settings.write_text(content, encoding="utf-8")
    assert machine.run("--yes") == 1
    assert settings.read_text(encoding="utf-8") == content
    assert not machine.claude_md.exists()
    assert f"{settings}: {reason}" in capsys.readouterr().err


def test_a_second_run_changes_no_byte(machine: Machine, capsys: pytest.CaptureFixture[str]) -> None:
    """NFR-05: unchanged answers on a re-run write nothing, under -y or interactively."""
    assert machine.run("--yes") == 0
    first: dict[str, bytes] = tree(machine.root)
    assert machine.run("--yes") == 0
    assert machine.run(answers=("", "", "", "", "", "", "", "", "")) == 0
    assert tree(machine.root) == first
    assert capsys.readouterr().out.count("Models: nothing to change.") == 2


def test_copilot_home_wins_and_is_read_from_the_injected_environment(machine: Machine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """NFR-06: a ``COPILOT_HOME`` with spaces and non-ASCII characters, outside the home, wins over ``~/.copilot``."""
    moved: Path = tmp_path / "Co pilot hömé ✓"
    moved.mkdir()
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path / "process-only"))
    machine.environ["COPILOT_HOME"] = str(moved)
    assert machine.run("--yes") == 0
    assert (moved / "copilot-instructions.md").read_text(encoding="utf-8") == COPILOT_BLOCK + "\n"
    assert not (machine.root / ".copilot" / "copilot-instructions.md").exists()
    assert not (tmp_path / "process-only").exists()
    assert f"COPILOT_HOME moves the file to {moved / 'copilot-instructions.md'}" in capsys.readouterr().out


def test_one_unwritable_host_does_not_stop_the_other(machine: Machine, capsys: pytest.CaptureFixture[str]) -> None:
    """NFR-07: a directory where Copilot's file belongs cannot be replaced; Claude Code is still written."""
    machine.copilot_md.mkdir()
    assert machine.run("--yes") == 1
    assert stored_choices(machine.claude_md.read_text(encoding="utf-8")) == DEFAULTS
    assert machine.copilot_md.is_dir()
    assert list(machine.copilot_md.parent.iterdir()) == [machine.copilot_md]
    out: str
    err: str
    out, err = capsys.readouterr()
    assert "copilot: failed" in out
    assert str(machine.copilot_md) in err


def test_a_failure_before_the_replace_leaves_the_old_bytes(machine: Machine, monkeypatch: pytest.MonkeyPatch) -> None:
    """NFR-08: the new text goes to a temporary file first; a failed replace keeps the old file and removes the temporary one."""
    machine.copilot_md.write_bytes(b"old\r\n")
    monkeypatch.setattr("pathlib.Path.replace", Mock(side_effect=OSError("disk full")))
    assert machine.run(answers=("copilot", "", "", "", "", "y")) == 1
    assert machine.copilot_md.read_bytes() == b"old\r\n"
    assert list(machine.copilot_md.parent.iterdir()) == [machine.copilot_md]


@pytest.mark.parametrize(("folder", "name"), [(".claude", "CLAUDE.md"), (".copilot", "copilot-instructions.md")], ids=["claude-code", "copilot"])
def test_yes_skips_a_host_folder_linked_into_a_repo_and_fails(machine: Machine, folder: str, name: str) -> None:
    """Regression (NFR-16): a host folder that is itself a link into a repository is not a boundary; only a folder the environment names is."""
    links: dict[Path, Path] = {machine.root / folder: machine.repo, machine.root / folder / name: machine.repo / name}
    assert machine.run("--yes", resolve=lambda path: links.get(path, path)) == 1
    assert not (machine.root / folder / name).exists()
    assert not (machine.repo / name).exists()


def test_yes_skips_a_copilot_file_linked_into_a_repo_and_fails(machine: Machine, capsys: pytest.CaptureFixture[str]) -> None:
    """NFR-16 for Copilot: a link resolving into the repository is never written under -y."""
    linked: Path = machine.repo / "copilot-instructions.md"
    assert machine.run("--yes", resolve=lambda path: linked if path == machine.copilot_md else path) == 1
    assert not linked.exists()
    assert not machine.copilot_md.exists()
    assert machine.claude_md.is_file()
    out: str
    err: str
    out, err = capsys.readouterr()
    assert f"{machine.copilot_md} is a link to {linked}" in err
    assert f"skipped  {machine.copilot_md} (link outside home)" in out


def test_a_deselected_configured_host_is_listed_and_left_alone(machine: Machine, capsys: pytest.CaptureFixture[str]) -> None:
    machine.copilot_md.write_text("mine\n" + COPILOT_BLOCK + "\n", encoding="utf-8", newline="")
    assert machine.run(answers=("claude-code", "", "", "", "", "y")) == 0
    assert machine.copilot_md.read_text(encoding="utf-8") == "mine\n" + COPILOT_BLOCK + "\n"
    out: str = capsys.readouterr().out
    assert "copilot: still configured; delete the block to remove it" in out
    assert str(machine.copilot_md) in out


REVIEWER_GUARD: str = "You are a reviewer. Do not load the `python-code-standards` or `design-spec` skills and do not open `CLAUDE.md`, `.github/copilot-instructions.md` or `.claude/`. Use the `review-standards` skill."
REVIEW_BLOCK: str = f"<!-- python-code-standards:review -->\n## Review scope\n\n{REVIEWER_GUARD}\n<!-- /python-code-standards:review -->"
"""The block setup keeps in Codex's ``AGENTS.md`` when a host reviews with Codex."""


def test_yes_with_a_codex_reviewer_writes_the_review_scope_block(machine: Machine, capsys: pytest.CaptureFixture[str]) -> None:
    assert machine.run("--yes") == 0
    assert machine.agents_md.read_text(encoding="utf-8") == REVIEW_BLOCK + "\n"
    assert "codex: written" in capsys.readouterr().out


def test_the_review_scope_block_stays_under_100_words() -> None:
    """NFR-12 for Codex's file."""
    assert len(REVIEW_BLOCK.split()) < 100


def test_codex_home_moves_the_review_scope_block(machine: Machine, tmp_path: Path) -> None:
    moved: Path = tmp_path / "codex home"
    machine.environ["CODEX_HOME"] = str(moved)
    assert machine.run("--yes") == 0
    assert (moved / "AGENTS.md").read_text(encoding="utf-8") == REVIEW_BLOCK + "\n"
    assert not (machine.root / ".codex").exists()


def test_no_codex_reviewer_writes_nothing_for_codex(machine: Machine, capsys: pytest.CaptureFixture[str]) -> None:
    assert machine.run(answers=("claude-code", "", "", "claude", "", "y")) == 0
    assert not (machine.root / ".codex").exists()
    assert "codex:" not in capsys.readouterr().out


def test_the_review_scope_block_keeps_the_users_text_and_a_models_block(machine: Machine) -> None:
    """The review markers differ from the models markers, so the two blocks never merge into each other."""
    mine: str = f"# Mine\r\n{render_block(CHOSEN)}\r\n"
    machine.agents_md.parent.mkdir()
    machine.agents_md.write_text(mine, encoding="utf-8", newline="")
    assert machine.run("--yes") == 0
    assert machine.agents_md.read_text(encoding="utf-8", newline="") == mine + "\n" + REVIEW_BLOCK + "\n"
    stale: str = mine + "\n" + REVIEW_BLOCK.replace("## Review scope", "## Old scope") + "\n"
    machine.agents_md.write_text(stale, encoding="utf-8", newline="")
    assert machine.run("--yes") == 0
    assert machine.agents_md.read_text(encoding="utf-8", newline="") == mine + "\n" + REVIEW_BLOCK + "\n"


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        (b"<!-- python-code-standards:review -->\nmine\n", "<!-- python-code-standards:review --> has no <!-- /python-code-standards:review --> after it"),
        (f"{REVIEW_BLOCK}\n{REVIEW_BLOCK}\n".encode(), "2 start and 2 end markers; it may hold one review scope block only"),
        (b"\xff not utf-8", "cannot be read"),
    ],
    ids=["orphan-start", "two-blocks", "unreadable"],
)
def test_an_invalid_agents_md_is_skipped_and_fails(machine: Machine, capsys: pytest.CaptureFixture[str], content: bytes, reason: str) -> None:
    machine.agents_md.parent.mkdir()
    machine.agents_md.write_bytes(content)
    assert machine.run("--yes") == 1
    assert machine.agents_md.read_bytes() == content
    assert stored_choices(machine.claude_md.read_text(encoding="utf-8")) == DEFAULTS
    out: str
    err: str
    out, err = capsys.readouterr()
    assert f"{machine.agents_md}: {reason}" in err
    assert "codex: skipped (invalid)" in out


def test_yes_skips_an_agents_md_linked_into_a_repo_and_fails(machine: Machine, capsys: pytest.CaptureFixture[str]) -> None:
    """NFR-16 for Codex: on this project's own machine ``~/.codex/AGENTS.md`` links into the repository."""
    linked: Path = machine.repo / "AGENTS.md"
    assert machine.run("--yes", resolve=lambda path: linked if path == machine.agents_md else path) == 1
    assert not linked.exists()
    assert not machine.agents_md.exists()
    assert f"{machine.agents_md} is a link to {linked}" in capsys.readouterr().err


def test_an_agents_override_is_reported(machine: Machine, capsys: pytest.CaptureFixture[str]) -> None:
    """NFR-15: Codex reads ``AGENTS.override.md`` instead of ``AGENTS.md``."""
    override: Path = machine.agents_md.parent / "AGENTS.override.md"
    override.parent.mkdir()
    override.write_text("mine\n", encoding="utf-8")
    assert machine.run("--yes") == 0
    assert f"{override} exists, and Codex reads it instead of {machine.agents_md}, so the review scope block will be ignored." in capsys.readouterr().out


@pytest.fixture
def modules(tmp_path: Path) -> Path:
    """A modules folder as the setup script stages it: one subfolder per skill."""
    folder: Path = tmp_path / "modules"
    (folder / "python-code-standards" / "tools").mkdir(parents=True)
    (folder / "python-code-standards" / "SKILL.md").write_bytes(b"coding skill\n")
    (folder / "python-code-standards" / "tools" / "check.py").write_bytes(b"print('ok')\r\n")
    (folder / "review-standards").mkdir()
    (folder / "review-standards" / "SKILL.md").write_bytes(b"review skill\n")
    return folder


MANAGED: dict[str, bytes] = {".managed-by": b"python-code-standards setup\n"}
CODING_FILES: dict[str, bytes] = {"SKILL.md": b"coding skill\n", "tools/check.py": b"print('ok')\r\n", **MANAGED}
REVIEW_FILES: dict[str, bytes] = {"SKILL.md": b"review skill\n", **MANAGED}


def installed(folder: Path) -> dict[str, bytes]:
    """Return every file under ``folder`` by its POSIX path inside, with its bytes; empty when the folder is missing."""
    return {path.relative_to(folder).as_posix(): path.read_bytes() for path in sorted(folder.rglob("*")) if path.is_file()}


def skill_dirs(root: Path) -> set[str]:
    """Return every directory under ``root`` that setup marked as installed, relative to it."""
    return {path.parent.relative_to(root).as_posix() for path in root.rglob(".managed-by")}


def test_yes_installs_each_skill_where_section_6a_places_it(machine: Machine, modules: Path) -> None:
    """NFR-11 for {claude-code, copilot} with a Codex reviewer: no coding skill in ``~/.agents/skills``, the one directory Codex scans in a home."""
    before: dict[str, bytes] = tree(machine.repo)
    assert machine.run("--yes", "--modules", str(modules)) == 0
    assert tree(machine.repo) == before
    assert skill_dirs(machine.root) == {
        ".claude/skills/python-code-standards",
        ".copilot/skills/python-code-standards",
        ".copilot/skills/review-standards",
        ".agents/skills/review-standards",
    }
    assert installed(machine.root / ".claude" / "skills" / "python-code-standards") == CODING_FILES
    assert installed(machine.root / ".agents" / "skills") == {f"review-standards/{name}": text for name, text in REVIEW_FILES.items()}


def test_a_claude_reviewer_gets_the_review_skill_beside_the_coding_skill(machine: Machine, modules: Path) -> None:
    assert machine.run("--modules", str(modules), answers=("claude-code", "", "", "claude", "", "y")) == 0
    assert skill_dirs(machine.root) == {".claude/skills/python-code-standards", ".claude/skills/review-standards"}


def test_no_copilot_reviewer_installs_no_review_skill(machine: Machine, modules: Path) -> None:
    assert machine.run("--modules", str(modules), answers=("copilot", "", "", "none", "", "y")) == 0
    assert skill_dirs(machine.root) == {".copilot/skills/python-code-standards"}


def test_copilot_home_moves_the_copilot_skills(machine: Machine, modules: Path, tmp_path: Path) -> None:
    moved: Path = tmp_path / "copilot home"
    moved.mkdir()
    machine.environ["COPILOT_HOME"] = str(moved)
    assert machine.run("--modules", str(modules), answers=("copilot", "", "", "", "", "y")) == 0
    assert skill_dirs(moved) == {"skills/python-code-standards", "skills/review-standards"}


def test_an_unmarked_skill_directory_is_reported_and_left_alone(machine: Machine, modules: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """NFR-14: a directory setup did not install is never changed."""
    mine: Path = machine.root / ".claude" / "skills" / "python-code-standards"
    mine.mkdir(parents=True)
    (mine / "SKILL.md").write_bytes(b"my own\n")
    assert machine.run("--yes", "--modules", str(modules)) == 0
    assert installed(mine) == {"SKILL.md": b"my own\n"}
    assert f"{mine} is not managed by setup; left as is." in capsys.readouterr().out


def test_a_linked_skill_directory_is_reported_and_left_alone(machine: Machine, modules: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """NFR-14: on this project's own machine the skill directories are links into the repository."""
    link: Path = machine.root / ".agents" / "skills" / "review-standards"
    clone: Path = machine.repo / "review-standards"
    assert machine.run("--yes", "--modules", str(modules), resolve=lambda path: clone if path == link else path) == 0
    assert not link.exists()
    assert not clone.exists()
    assert f"{link} is a link to {clone}; not managed by setup; left as is." in capsys.readouterr().out


def test_a_marked_skill_directory_is_brought_up_to_date(machine: Machine, modules: Path) -> None:
    mine: Path = machine.root / ".claude" / "skills" / "python-code-standards"
    mine.mkdir(parents=True)
    (mine / ".managed-by").write_bytes(MANAGED[".managed-by"])
    (mine / "SKILL.md").write_bytes(b"old\n")
    (mine / "extra.md").write_bytes(b"left\n")
    assert machine.run("--yes", "--modules", str(modules)) == 0
    assert installed(mine) == {**CODING_FILES, "extra.md": b"left\n"}


def test_a_second_run_with_modules_changes_no_byte(machine: Machine, modules: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """NFR-05 with every module and the installer copy."""
    installer: Path = tmp_path / "setup-standards.sh"
    installer.write_bytes(b"#!/usr/bin/env bash\r\necho setup\n")
    argv: tuple[str, ...] = ("--yes", "--modules", str(modules), "--installer", str(installer))
    assert machine.run(*argv) == 0
    first: dict[str, bytes] = tree(machine.root)
    capsys.readouterr()
    assert machine.run(*argv) == 0
    assert tree(machine.root) == first
    assert "Models: nothing to change." in capsys.readouterr().out


@pytest.mark.parametrize(
    ("answers", "stale"),
    [
        (("claude-code", "", "", "claude", "", "y"), ".agents/skills/review-standards"),
        (("claude-code", "", "", "", "", "y"), ".claude/skills/review-standards"),
    ],
    ids=["codex-to-claude", "claude-to-codex"],
)
def test_a_marked_skill_no_longer_wanted_is_listed_not_removed(machine: Machine, modules: Path, capsys: pytest.CaptureFixture[str], answers: tuple[str, ...], stale: str) -> None:
    folder: Path = machine.root / stale
    folder.mkdir(parents=True)
    (folder / ".managed-by").write_bytes(MANAGED[".managed-by"])
    assert machine.run("--modules", str(modules), answers=answers) == 0
    assert installed(folder) == MANAGED
    assert f"{folder} was installed by setup and is no longer wanted; delete it to remove it." in capsys.readouterr().out


def test_yes_skips_a_skill_file_linked_outside_home_and_fails(machine: Machine, modules: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """NFR-16 inside a marked directory: a file that is a link out of the home directory is not written under -y."""
    mine: Path = machine.root / ".claude" / "skills" / "python-code-standards"
    mine.mkdir(parents=True)
    (mine / ".managed-by").write_bytes(MANAGED[".managed-by"])
    linked: Path = machine.repo / "SKILL.md"
    assert machine.run("--yes", "--modules", str(modules), resolve=lambda path: linked if path == mine / "SKILL.md" else path) == 1
    assert not linked.exists()
    assert not (mine / "SKILL.md").exists()
    assert f"{mine / 'SKILL.md'} is a link to {linked}" in capsys.readouterr().err


def test_module_files_are_listed_by_path_only(machine: Machine, modules: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert machine.run("--modules", str(modules), answers=("claude-code", "", "", "claude", "", "n")) == 0
    out: str = capsys.readouterr().out
    assert f"  write    {machine.root / '.claude' / 'skills' / 'python-code-standards' / 'SKILL.md'}\n  write" in out
    assert "\ncoding skill\n" not in out


def test_yes_keeps_a_copy_of_the_installer(machine: Machine, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    installer: Path = tmp_path / "setup-standards.sh"
    installer.write_bytes(b"#!/usr/bin/env bash\r\necho setup\n")
    assert machine.run("--yes", "--installer", str(installer)) == 0
    assert (machine.root / ".local" / "share" / "python-code-standards" / "setup-standards.sh").read_bytes() == installer.read_bytes()
    assert "installer: written" in capsys.readouterr().out


def test_yes_skips_an_installer_copy_linked_outside_home_and_fails(machine: Machine, tmp_path: Path) -> None:
    installer: Path = tmp_path / "setup-standards.sh"
    installer.write_bytes(b"echo setup\n")
    copy: Path = machine.root / ".local" / "share" / "python-code-standards" / "setup-standards.sh"
    assert machine.run("--yes", "--installer", str(installer), resolve=lambda path: installer if path == copy else path) == 1
    assert not copy.exists()
    assert installer.read_bytes() == b"echo setup\n"


@pytest.mark.parametrize(
    ("answers", "expected", "absent"),
    [
        (
            ("claude-code copilot", "", "", "", "", "", "", "", "", "y"),
            [
                "claude-code, reviewer codex: structural: the coding skill is in no directory Codex scans",
                "copilot, reviewer copilot: advisory: review-standards shares Copilot's skills directory with the coding skill",
                "overlap: Copilot (CLI and VS Code) also scans ~/.agents/skills, so it sees review-standards.",
                "overlap: VS Code's Copilot also reads ~/.claude/skills, so it sees the Claude Code copy of python-code-standards.",
            ],
            [],
        ),
        (
            ("claude-code", "", "", "claude", "", "y"),
            ["claude-code, reviewer claude: advisory: review-standards shares ~/.claude/skills with the coding skill"],
            ["overlap:", "reviewer codex"],
        ),
        (("copilot", "", "", "none", "", "y"), ["copilot, reviewer none: no reviewer, so no review skill is installed."], ["overlap:"]),
    ],
    ids=["both-hosts", "claude-reviewer", "no-reviewer"],
)
def test_the_summary_states_the_guarantee_and_the_overlaps(machine: Machine, capsys: pytest.CaptureFixture[str], answers: tuple[str, ...], expected: list[str], absent: list[str]) -> None:
    """NFR-11: the remaining overlaps of section 6A for the selected hosts, and the guarantee level per reviewer."""
    assert machine.run(answers=answers) == 0
    out: str = capsys.readouterr().out
    assert "Review isolation (instructions narrow what a model loads; they do not forbid it):" in out
    line: str
    for line in expected:
        assert line in out
    for line in absent:
        assert line not in out


@pytest.mark.parametrize(("in_home", "in_repo"), [(True, False), (False, True), (False, False)], ids=["home-only", "repo-only", "neither"])
def test_a_coding_skill_codex_scans_breaks_the_structural_guarantee(machine: Machine, capsys: pytest.CaptureFixture[str], *, in_home: bool, in_repo: bool) -> None:
    """The guarantee is checked, not assumed: a coding skill in ``~/.agents/skills`` or the target repository's ``.agents/skills`` is in Codex's reach.

    Regression: only the home directory was checked, so a repository copy still read "structural".
    """
    copies: list[Path] = [root / ".agents" / "skills" / "python-code-standards" for root, wanted in ((machine.root, in_home), (machine.repo, in_repo)) if wanted]
    before: dict[str, bytes] = tree(machine.repo)
    copy: Path
    for copy in copies:
        copy.mkdir(parents=True)
    assert machine.run("--yes") == 0
    out: str = capsys.readouterr().out
    assert [line for line in out.splitlines() if "not structural" in line] == [f"  not structural while {copy} exists: Codex scans that directory and setup does not manage it; remove it by hand." for copy in copies]
    assert tree(machine.repo) == before


def test_an_unknown_stored_provider_is_reported_without_a_review_skill(home: Home, capsys: pytest.CaptureFixture[str]) -> None:
    """A hand-edited block may name a provider setup does not offer."""
    home.claude.mkdir()
    (home.claude / "CLAUDE.md").write_text(render_block(replace(DEFAULTS, reviewer_provider="gemini")) + "\n", encoding="utf-8")
    assert home.run("--yes") == 0
    assert "claude-code, reviewer gemini: unknown provider, so no review skill is installed." in capsys.readouterr().out


def test_an_unreadable_file_in_a_marked_directory_is_rewritten(machine: Machine, modules: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mine: Path = machine.root / ".claude" / "skills" / "python-code-standards"
    mine.mkdir(parents=True)
    (mine / ".managed-by").write_bytes(MANAGED[".managed-by"])
    (mine / "SKILL.md").write_bytes(b"coding skill\n")
    real: Callable[[Path], bytes] = Path.read_bytes

    def read_bytes(path: Path) -> bytes:
        if path == mine / "SKILL.md":
            raise PermissionError(path)
        return real(path)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    assert machine.run("--yes", "--modules", str(modules)) == 0
    monkeypatch.undo()
    assert installed(mine) == CODING_FILES
