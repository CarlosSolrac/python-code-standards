"""The setup script embeds the skill's templates; assert the copies have not drifted.

``setup/setup-standards.sh`` is self-contained so it can run on a host with
no clone of this repo. That duplication is only safe if drift fails here. The
script's own check must also leave the repository's existing files unmodified.
"""

from __future__ import annotations

import io
import json
import re
import sys
import tomllib
from code import InteractiveInterpreter
from pathlib import Path
from types import CodeType

import pytest

from skill.tools.hooks.stop_gate import VENDORED_TOOLS, run_command
from skill.tools.setup_files import PYPROJECT, digest, table_digest
from skill.tools.template_history import templates

REPO_ROOT: Path = Path(__file__).resolve().parent.parent
SETUP_SCRIPT: Path = REPO_ROOT / "setup" / "setup-standards.sh"


def heredoc(delimiter: str) -> str:
    """Return the body of the first ``<<'<delimiter>'`` heredoc in the setup script.

    Args:
        delimiter: The quoted heredoc delimiter, e.g. ``PYEOF``.

    Returns:
        The text between the opening line and the closing delimiter line,
        including the trailing newline of the last content line.
    """
    lines: list[str] = SETUP_SCRIPT.read_text(encoding="utf-8").splitlines(keepends=True)
    opener: str = f"<<'{delimiter}'"
    start: int | None = None
    index: int
    line: str
    for index, line in enumerate(lines):
        if opener in line:
            start = index + 1
            break
    if start is None:
        pytest.fail(f"no heredoc {opener} in {SETUP_SCRIPT.name}")
    end: int | None = None
    for index in range(start, len(lines)):
        if lines[index].rstrip("\n") == delimiter:
            end = index
            break
    if end is None:
        pytest.fail(f"heredoc {opener} is not closed in {SETUP_SCRIPT.name}")
    return "".join(lines[start:end])


@pytest.mark.parametrize(
    ("script", "message"),
    [
        ("echo no heredoc here\n", "no heredoc <<'PYEOF' in script.sh"),
        ("cat <<'PYEOF'\nbody\n", "heredoc <<'PYEOF' is not closed in script.sh"),
    ],
    ids=["no-opener", "no-closer"],
)
def test_heredoc_fails_loudly_when_the_script_lacks_the_block(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, script: str, message: str) -> None:
    """A renamed or truncated heredoc must fail the drift tests, never compare against an empty string."""
    path: Path = tmp_path / "script.sh"
    path.write_text(script, encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "SETUP_SCRIPT", path)
    with pytest.raises(pytest.fail.Exception, match=re.escape(message)):
        heredoc("PYEOF")


@pytest.mark.parametrize(
    ("delimiter", "asset"),
    [
        ("PYEOF", "skill/tools/check_declarations.py"),
        ("TOML", "skill/assets/pyproject-baseline.toml"),
        ("YAML", "skill/assets/pre-commit-config.yaml"),
        ("ATTR", "skill/assets/gitattributes"),
        ("CI", "skill/assets/ci.yml"),
        ("GUARDEOF", "skill/tools/hooks/guard_protected.py"),
        ("STOPEOF", "skill/tools/hooks/stop_gate.py"),
        ("HOOKSINIT", "skill/tools/hooks/__init__.py"),
        ("SETTINGS", "skill/assets/claude-settings.json"),
        ("CHANGESEOF", "skill/tools/changes.py"),
        ("SUPPRESSEOF", "skill/tools/check_suppressions.py"),
        ("COVRECEOF", "skill/tools/check_coverage_records.py"),
        ("ALLOWEOF", "skill/assets/suppressions.toml"),
        ("MUTEOF", "skill/tools/mutation.sh"),
        ("MUTCI", "skill/assets/mutation.yml"),
        ("BRIEFEOF", "skill/tools/review_brief.py"),
        ("SETUPEOF", "skill/tools/setup_files.py"),
        ("MODELSEOF", "skill/tools/setup_models.py"),
        ("MOD_SKILL", "skill/SKILL.md"),
        ("MOD_CONFORMANCE", "skill/assets/conformance.py"),
        ("MOD_DOMAINS", "skill/references/domains.md"),
        ("MOD_SETUP", "skill/references/setup.md"),
        ("MOD_SQL", "skill/references/sql-duckdb.md"),
        ("MOD_TESTING", "skill/references/testing.md"),
        ("MOD_TYPING", "skill/references/typing.md"),
        ("MOD_TOOLSINIT", "skill/tools/__init__.py"),
        ("MOD_PASSTHROUGH", "skill/tools/check_passthrough.py"),
        ("MOD_HISTORY", "skill/tools/template_history.py"),
        ("MOD_VENDOR", "skill/tools/vendor_templates.py"),
        ("MOD_REVIEW", "../review-standards/SKILL.md"),
    ],
    ids=[
        "check_declarations",
        "pyproject",
        "pre-commit",
        "gitattributes",
        "ci",
        "guard_protected",
        "stop_gate",
        "hooks-init",
        "claude-settings",
        "changes",
        "check_suppressions",
        "check_coverage_records",
        "suppressions-allow-list",
        "mutation-runner",
        "mutation-workflow",
        "review-brief",
        "setup-files",
        "setup-models",
        "skill",
        "conformance",
        "domains",
        "setup-reference",
        "sql-duckdb",
        "testing",
        "typing",
        "tools-init",
        "check_passthrough",
        "template_history",
        "vendor_templates",
        "review-skill",
    ],
)
@pytest.mark.no_mutation
def test_embedded_template_matches_source(delimiter: str, asset: str) -> None:
    """Each embedded heredoc is identical to the file it vendors.

    The ``pyproject.toml`` heredoc keeps the baseline's ``name = "example-project"``
    and the script rewrites it at run time, so the stored text still matches.
    """
    source: str = (REPO_ROOT / asset).read_text(encoding="utf-8")
    assert heredoc(delimiter) == source


def test_embedded_history_covers_every_current_template() -> None:
    """Each template's digest is in the embedded history, so setup recognizes what it writes today.

    A template changed without regenerating the history fails here; run
    ``uv run python -m skill.tools.template_history``.
    """
    known: dict[str, dict[str, list[str]]] = json.loads(heredoc("HASHEOF"))
    written: dict[str, str] = templates(SETUP_SCRIPT.read_text(encoding="utf-8"))
    assert set(written) - {PYPROJECT} == set(known["files"])
    path: str
    text: str
    for path, text in written.items():
        if path != PYPROJECT:
            assert digest(text) in known["files"][path], path
    name: str
    value: object
    for name, value in tomllib.loads(written[PYPROJECT])["tool"].items():
        assert table_digest(value) in known["tables"][f"tool.{name}"], name


def staged_modules() -> dict[str, str]:
    """Return each file the setup script stages for the skills it installs, by its path in the modules folder, with its text.

    Read from the script rather than run: a ``module_file`` heredoc holds a file itself,
    and each line of the ``REUSED`` heredoc copies a file the script staged from another
    heredoc, with ``write_file`` into ``$FILES`` or with ``cat`` into ``$WORK``.
    """
    script: str = SETUP_SCRIPT.read_text(encoding="utf-8")
    staged: dict[str, str] = {}
    modules: dict[str, str] = {}
    match: re.Match[str]
    for match in re.finditer(r"""^(?:write_file (\S+)|cat >"\$WORK/(\S+)"|module_file (\S+)) <<'(\w+)'$""", script, re.MULTILINE):
        if match.group(3):
            modules[match.group(3)] = heredoc(match.group(4))
        else:
            staged[f"files/{match.group(1)}" if match.group(1) else match.group(2)] = heredoc(match.group(4))
    line: str
    for line in heredoc("REUSED").splitlines():
        source: str
        module: str
        source, module = line.split()
        modules[module] = staged[source]
    return modules


@pytest.mark.no_mutation
def test_setup_stages_every_tracked_skill_file_byte_identical() -> None:
    """The installed coding skill is every file git tracks under ``skill/`` but the package marker the repository's tests import it through; the review skill is its ``SKILL.md``.

    ``skill/tools/__init__.py`` and ``skill/tools/hooks/__init__.py`` stay, because the
    tools import each other relatively and run as ``python -m tools.<name>``.
    """
    tracked: list[str] = run_command(("git", "-C", str(REPO_ROOT), "ls-files", "--", "skill")).output.split()
    sources: dict[str, Path] = {f"python-code-standards/{path.removeprefix('skill/')}": REPO_ROOT / path for path in tracked if path != "skill/__init__.py"}
    sources["review-standards/SKILL.md"] = REPO_ROOT.parent / "review-standards" / "SKILL.md"
    modules: dict[str, str] = staged_modules()
    assert set(modules) == set(sources)
    path: str
    source: Path
    for path, source in sources.items():
        assert modules[path] == source.read_text(encoding="utf-8"), path


def test_vendored_tools_list_matches_what_setup_writes() -> None:
    """The coverage-record exemption covers exactly the Python files setup vendors."""
    written: set[str] = set(re.findall(r"^write_file (tools/\S+\.py) ", SETUP_SCRIPT.read_text(encoding="utf-8"), re.MULTILINE))
    assert written == VENDORED_TOOLS


def run_embedded_models(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *argv: str, stdin: str = "", status: int = 0) -> Path:
    """Run the setup script's copy of ``setup_models.py`` against a temporary home, as the script does, expecting exit ``status``.

    Returns:
        The temporary home's ``.claude`` directory; the real one is never touched.
    """
    home: Path = tmp_path / "home"
    home.mkdir(exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.delenv("COPILOT_HOME", raising=False)
    monkeypatch.setattr(sys, "argv", ["setup_models.py", *argv])
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin))
    # Compiled under a pseudo-filename, so coverage does not count the embedded copy as a project file.
    code: CodeType = compile(heredoc("MODELSEOF"), "<setup_models>", "exec")
    exit_info: pytest.ExceptionInfo[SystemExit]
    with pytest.raises(SystemExit) as exit_info:
        InteractiveInterpreter({"__name__": "__main__"}).runcode(code)
    assert exit_info.value.code == status
    return home / ".claude"


def settings_model(claude: Path) -> object:
    """Return the ``model`` key of ``settings.json``."""
    settings: dict[str, object] = json.loads((claude / "settings.json").read_text(encoding="utf-8"))
    return settings.get("model")


@pytest.mark.no_mutation
def test_setup_models_first_run_asks_then_writes_after_confirmation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    claude: Path = run_embedded_models(tmp_path, monkeypatch, stdin="\nsonnet\nhaiku\nclaude\nopus\ny\n")
    memory: str = (claude / "CLAUDE.md").read_text(encoding="utf-8")
    assert "<!-- python-code-standards:models -->" in memory
    assert "`haiku`" in memory
    assert "`claude`" in memory
    assert settings_model(claude) == "sonnet"


@pytest.mark.no_mutation
def test_setup_models_rerun_offers_the_stored_answers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty replies keep every stored answer; a new coordinator replaces the settings ``model``."""
    claude: Path = run_embedded_models(tmp_path, monkeypatch, stdin="\nsonnet\nhaiku\nclaude\nopus\ny\n")
    first: str = (claude / "CLAUDE.md").read_text(encoding="utf-8")
    run_embedded_models(tmp_path, monkeypatch, stdin="\n\n\n\n\n")
    assert (claude / "CLAUDE.md").read_text(encoding="utf-8") == first
    run_embedded_models(tmp_path, monkeypatch, stdin="\nopus\n\n\n\ny\n")
    assert (claude / "CLAUDE.md").read_text(encoding="utf-8") == first.replace("`sonnet`", "`opus`", 1)
    assert settings_model(claude) == "opus"


@pytest.mark.no_mutation
def test_setup_models_yes_writes_defaults_once_and_then_keeps_them(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    claude: Path = run_embedded_models(tmp_path, monkeypatch, "--yes")
    memory: Path = claude / "CLAUDE.md"
    assert settings_model(claude) == "sonnet"
    memory.write_text(memory.read_text(encoding="utf-8").replace("`sonnet`", "`mine`"), encoding="utf-8")
    run_embedded_models(tmp_path, monkeypatch, "--yes")
    assert "`mine`" in memory.read_text(encoding="utf-8")


@pytest.mark.no_mutation
def test_setup_models_fails_on_an_orphan_marker_and_writes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-zero status, which the setup script records and reports at the end as a failed run."""
    claude: Path = tmp_path / "home" / ".claude"
    claude.mkdir(parents=True)
    orphan: bytes = b"intro\n<!-- python-code-standards:models -->\nuser text kept\n"
    (claude / "CLAUDE.md").write_bytes(orphan)
    run_embedded_models(tmp_path, monkeypatch, "--yes", status=1)
    assert (claude / "CLAUDE.md").read_bytes() == orphan
    assert not (claude / "settings.json").exists()


@pytest.mark.no_mutation
def test_setup_models_yes_keeps_an_existing_settings_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    claude: Path = tmp_path / "home" / ".claude"
    claude.mkdir(parents=True)
    (claude / "settings.json").write_text('{"model": "haiku", "env": {}}', encoding="utf-8")
    run_embedded_models(tmp_path, monkeypatch, "--yes")
    assert json.loads((claude / "settings.json").read_text(encoding="utf-8")) == {"model": "haiku", "env": {}}
    assert (claude / "CLAUDE.md").is_file()


COPILOT_BLOCK: str = (
    "<!-- python-code-standards:models -->\n## Models (Copilot)\n\n"
    "- Coordinator model (main session default; runs the tests): `Claude Sonnet 5.5`\n"
    "- Coding model (agents that write code): `Claude Opus 5.5`\n"
    "- Adversarial code-review provider: `copilot`\n"
    "- Adversarial code-review model: `GPT-6 Astra`\n\n"
    "Other agents' instruction files (`CLAUDE.md`, `.claude/`, `AGENTS.md`) are not for you; do not open them unless a change touches them.\n"
    "<!-- /python-code-standards:models -->\n"
)
"""Copilot's defaults as the embedded copy writes them into a new ``copilot-instructions.md``."""


@pytest.mark.no_mutation
def test_setup_models_yes_configures_copilot_alone_when_only_its_home_exists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    copilot: Path = tmp_path / "home" / ".copilot"
    copilot.mkdir(parents=True)
    claude: Path = run_embedded_models(tmp_path, monkeypatch, "--yes")
    assert (copilot / "copilot-instructions.md").read_text(encoding="utf-8") == COPILOT_BLOCK
    assert not claude.exists()


@pytest.mark.no_mutation
def test_setup_models_configures_both_hosts_after_one_confirmation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    claude: Path = run_embedded_models(tmp_path, monkeypatch, stdin="claude-code, copilot\n\n\n\n\n\n\n\n\ny\n")
    assert settings_model(claude) == "sonnet"
    assert "`gpt-5.4`" in (claude / "CLAUDE.md").read_text(encoding="utf-8")
    assert (claude.parent / ".copilot" / "copilot-instructions.md").read_text(encoding="utf-8") == COPILOT_BLOCK


def test_setup_passes_yes_to_setup_models_only_with_yes() -> None:
    """Without ``-y`` the questions are asked; ``--update`` and ``--force`` mean nothing to them."""
    commands: list[str] = script_commands()
    assert "MODEL_FLAGS+=(--yes)" in commands
    assert [command for command in commands if '"$WORK/setup_models.py" ' in command] == [
        'uv run --no-project --python 3.13 python "$WORK/setup_models.py" --modules "$MODULES" --installer "$INSTALLER" ${MODEL_FLAGS[@]+"${MODEL_FLAGS[@]}"} || MODELS_RC=$?'
    ]


def test_setup_names_itself_before_leaving_the_directory_it_was_run_from() -> None:
    """``--installer`` must name this script after ``cd "$REPO_ROOT"``, so the path is made absolute first."""
    commands: list[str] = script_commands()
    assert 'INSTALLER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"' in commands
    assert commands.index('INSTALLER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"') < commands.index('cd "$REPO_ROOT"')


def test_setup_finishes_but_fails_when_the_models_step_fails() -> None:
    """Any non-zero status from ``setup_models.py`` (refused, bad arguments, a crash) lets setup carry on, then fail.

    Under ``set -e`` an uncaptured failure would stop setup before the gates are installed;
    uncaught, it would end with ``checks: PASS`` although no models were recorded.
    """
    commands: list[str] = script_commands()
    models: int = next(index for index, command in enumerate(commands) if "setup_models.py" in command)
    assert commands[models].endswith(" || MODELS_RC=$?")
    assert commands[models - 1] == "MODELS_RC=0"
    assert "exit" not in commands[models + 1]
    report: int = commands.index('if [ "$MODELS_RC" -ne 0 ]; then')
    assert commands[report + 1 : report + 3] == ["CHECK_RC=1", "fi"]
    assert commands.index("CHECK_RC=0") < report < commands.index('if [ "$CHECK_RC" -eq 0 ]; then')


def test_setup_failure_report_claims_only_that_the_checks_modified_nothing() -> None:
    """A failed run may follow writes by setup itself (a ``-y`` models step can write one file and skip a linked one)."""
    script: str = SETUP_SCRIPT.read_text(encoding="utf-8")
    assert "printf '\\nchecks: FAILED or INCOMPLETE -- read the output above. The checks modified no file; setup may have written files above.\\n'" in script
    assert "No file was modified" not in script


def script_commands() -> list[str]:
    """Return the setup script's executable lines, outside heredocs, comments, and messages."""
    commands: list[str] = []
    closer: str | None = None
    line: str
    for line in SETUP_SCRIPT.read_text(encoding="utf-8").splitlines():
        if closer is not None:
            if line == closer:
                closer = None
            continue
        stripped: str = line.strip()
        if "<<'" in stripped:
            closer = stripped.split("<<'")[1].split("'")[0]
            continue
        if stripped and not stripped.startswith(("#", "printf")):
            commands.append(stripped)
    return commands


def test_setup_check_runs_no_hooks() -> None:
    """The check never runs pre-commit, so no hook from any config can rewrite files.

    A repository that already has a ``.pre-commit-config.yaml`` keeps it, and its
    hooks (``end-of-file-fixer``, Black, isort) modify files when run.
    """
    assert [command for command in script_commands() if "pre-commit run" in command] == []


def test_setup_check_runs_ruff_in_report_mode() -> None:
    """Ruff runs without ``--fix`` and the formatter only checks.

    Run over existing code, the fixer deletes unused imports and the formatter
    rewrites files before anyone has reviewed the change.
    """
    command: str
    for command in script_commands():
        if "ruff check" in command:
            assert "--no-fix" in command, command
        if "ruff format" in command:
            assert "--check" in command, command


def test_setup_check_reports_missing_tools() -> None:
    """Each tool runs through ``check``, which reports a tool the project lacks as not run.

    An existing ``pyproject.toml`` is kept as it is, so the project environment may
    lack Ruff, Pyright, or MyPy; launching one directly fails as if the code did.
    """
    tools: tuple[str, ...] = ("ruff ", "pyright", "mypy", "tools/check_declarations.py")
    checked: list[str] = [command for command in script_commands() if any(tool in command for tool in tools) and not command.startswith("write_file")]
    assert len(checked) == 5, checked
    command: str
    for command in checked:
        assert command.startswith("check "), command


def test_setup_never_stages_backups() -> None:
    """``--force`` saves replaced files as ``<name>.orig``; staging them would commit the user's old copies."""
    assert [command for command in script_commands() if command.startswith("git add")] == ["git add -A -- . ':(exclude)*.orig' ':(exclude)*.orig.*'"]


def test_setup_installs_the_git_hook_only_when_pre_commit_is_installed() -> None:
    """A project whose dev group lacks pre-commit is told the hook was not installed.

    Run unguarded, ``uv run pre-commit install`` fails under ``set -e`` and aborts setup
    before it stages the files, runs the checks, or reports what is missing.
    """
    commands: list[str] = script_commands()
    install: int = commands.index("uv run pre-commit install")
    assert commands[install - 1 : install + 4] == [
        "if uv run --no-sync pre-commit --version >/dev/null 2>&1; then",
        "uv run pre-commit install",
        "else",
        'NOT_RUN+=("pre-commit git hook")',
        "fi",
    ]


def test_setup_finishes_but_fails_when_uv_add_fails() -> None:
    """``setup_files.py`` exits 3 when ``uv add`` fails: setup carries on, then reports the run incomplete.

    Any other failure still stops setup. Without this, a project whose checks never
    use the tool that failed to install would end with ``checks: PASS``.
    """
    commands: list[str] = script_commands()
    install: int = next(index for index, command in enumerate(commands) if "setup_files.py" in command)
    assert commands[install].endswith(" || SETUP_RC=$?")
    assert commands[install - 1] == "SETUP_RC=0"
    assert commands[install + 1 : install + 4] == ['if [ "$SETUP_RC" -ne 0 ] && [ "$SETUP_RC" -ne 3 ]; then', 'exit "$SETUP_RC"', "fi"]
    report: int = commands.index('if [ "$SETUP_RC" -eq 3 ]; then')
    assert commands[report + 1 : report + 3] == ["CHECK_RC=1", "fi"]
    assert report < commands.index('if [ "$CHECK_RC" -eq 0 ]; then')
