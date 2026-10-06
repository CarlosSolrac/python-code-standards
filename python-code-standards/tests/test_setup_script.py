"""The setup script embeds the skill's templates; assert the copies have not drifted.

``skill/assets/setup-standards.sh`` is self-contained so it can run on a host with
no clone of this repo. That duplication is only safe if drift fails here. The
script's own check must also leave the repository's existing files unmodified.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from skill.tools.hooks.stop_gate import VENDORED_TOOLS

REPO_ROOT: Path = Path(__file__).resolve().parent.parent
SETUP_SCRIPT: Path = REPO_ROOT / "skill" / "assets" / "setup-standards.sh"


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
    ],
)
def test_embedded_template_matches_source(delimiter: str, asset: str) -> None:
    """Each embedded heredoc is identical to the file it vendors.

    The ``pyproject.toml`` heredoc keeps the baseline's ``name = "example-project"``
    and the script rewrites it at run time, so the stored text still matches.
    """
    source: str = (REPO_ROOT / asset).read_text(encoding="utf-8")
    assert heredoc(delimiter) == source


def test_vendored_tools_list_matches_what_setup_writes() -> None:
    """The coverage-record exemption covers exactly the Python files setup vendors."""
    written: set[str] = set(re.findall(r"^write_file (tools/\S+\.py) ", SETUP_SCRIPT.read_text(encoding="utf-8"), re.MULTILINE))
    assert written == VENDORED_TOOLS


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
