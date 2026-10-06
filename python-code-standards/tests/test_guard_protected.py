"""Tests for the PreToolUse hook that asks before a quality gate is changed.

A miss here is silent: the edit goes through and a gate is weakened unseen, so
the allowed cases are asserted as explicitly as the protected ones.
"""

from __future__ import annotations

import io
import json
import runpy
import sys
from pathlib import Path
from typing import cast

import pytest

from skill.tools.hooks.guard_protected import main

GUARD: Path = Path(__file__).resolve().parent.parent / "skill" / "tools" / "hooks" / "guard_protected.py"


def decide(tool_name: str, tool_input: dict[str, str]) -> dict[str, object] | None:
    """Run the hook on one event; return its parsed decision, or None when it stays silent."""
    stdin: io.StringIO = io.StringIO(json.dumps({"tool_name": tool_name, "tool_input": tool_input}))
    stdout: io.StringIO = io.StringIO()
    assert main(stdin, stdout) == 0
    if not stdout.getvalue():
        return None
    output: dict[str, object] = json.loads(stdout.getvalue())
    return output


def asks(tool_name: str, tool_input: dict[str, str]) -> bool:
    """Return whether the hook asks the user before this tool call runs."""
    decision: dict[str, object] | None = decide(tool_name, tool_input)
    if decision is None:
        return False
    specific: dict[str, object] = cast("dict[str, object]", decision["hookSpecificOutput"])
    assert specific["hookEventName"] == "PreToolUse"
    return specific["permissionDecision"] == "ask"


@pytest.mark.parametrize(
    "path",
    [
        "pyproject.toml",
        "/repo/ruff.toml",
        "/repo/.ruff.toml",
        "/repo/setup.cfg",
        "/repo/mypy.ini",
        "/repo/pyrightconfig.json",
        "/repo/pytest.ini",
        "/repo/tox.ini",
        "/repo/.coveragerc",
        "/repo/.pre-commit-config.yaml",
        "/repo/.github/workflows/ci.yml",
        "/repo/tools/check_declarations.py",
        "/repo/tools/check_suppressions.py",
        "/repo/tools/check_coverage_records.py",
        "/repo/tools/changes.py",
        "/repo/tools/mutation.sh",
        "/repo/suppressions.toml",
        "/repo/tools/hooks/stop_gate.py",
        "/repo/.claude/settings.json",
        "/repo/.claude/settings.local.json",
        r"E:\repo\.github\workflows\ci.yml",
        r"E:\repo\pyproject.toml",
        # Windows filesystems ignore case, so these are the same protected files.
        r"E:\repo\.claude\SETTINGS.JSON",
        r"E:\repo\PyProject.toml",
        r"E:\repo\Tools\Hooks\stop_gate.py",
        r"E:\repo\.GitHub\Workflows\ci.yml",
    ],
)
@pytest.mark.parametrize("tool_name", ["Edit", "Write", "MultiEdit"])
def test_file_tool_on_protected_path_asks(tool_name: str, path: str) -> None:
    assert asks(tool_name, {"file_path": path})


@pytest.mark.parametrize(
    "path",
    ["/repo/src/app.py", "/repo/tests/test_app.py", "/repo/tools/report.py", "/repo/docs/pyproject.toml.md", "/repo/.claude/agents/x.md"],
)
def test_file_tool_on_ordinary_path_is_silent(path: str) -> None:
    assert decide("Edit", {"file_path": path}) is None


def test_reason_names_the_file_and_the_alternative() -> None:
    decision: dict[str, object] | None = decide("Edit", {"file_path": "/repo/pyproject.toml"})
    assert decision is not None
    specific: dict[str, object] = cast("dict[str, object]", decision["hookSpecificOutput"])
    assert specific["permissionDecisionReason"] == (
        "/repo/pyproject.toml defines a quality gate. Changing it can make a failing check pass without a fix, so the user must approve. If the goal is a passing check, fix the code instead."
    )


@pytest.mark.parametrize(
    ("command", "reason"),
    [
        ("uv add requests", "This command changes the project's dependencies, which needs the user's approval. Ask before adding, removing, or upgrading a package."),
        (
            "rm pyproject.toml",
            "This command appears to modify a file that defines a quality gate, which needs the user's approval. If the goal is a passing check, fix the code instead.",
        ),
    ],
    ids=["dependencies", "gate-file"],
)
def test_shell_reason_is_exact(command: str, reason: str) -> None:
    decision: dict[str, object] | None = decide("Bash", {"command": command})
    assert decision is not None
    specific: dict[str, object] = cast("dict[str, object]", decision["hookSpecificOutput"])
    assert specific["permissionDecisionReason"] == reason


@pytest.mark.parametrize(
    "event",
    [{"tool_name": "Read"}, {"tool_name": "Edit", "tool_input": {}}, {"tool_name": "Bash", "tool_input": {}}, {"tool_input": {"file_path": "pyproject.toml"}}],
    ids=["no-tool-input", "no-file-path", "no-command", "no-tool-name"],
)
def test_incomplete_event_is_silent(event: dict[str, object]) -> None:
    """A field missing from the event is never a crash; the hook stays silent."""
    stdout: io.StringIO = io.StringIO()
    assert main(io.StringIO(json.dumps(event)), stdout) == 0
    assert stdout.getvalue() == ""


@pytest.mark.parametrize(
    "command",
    [
        "uv add requests",
        "uv add --dev hypothesis",
        "uv remove requests",
        "uv lock --upgrade",
        "uv lock --upgrade-package ruff",
        "sed -i 's/100/90/' pyproject.toml",
        "sed -e 's/a/b/' -i.bak pyproject.toml",
        "echo '[tool.x]' >> pyproject.toml",
        "printf x > .pre-commit-config.yaml",
        "echo x > tools/check_declarations.py",
        "cat replacement.py > tools/hooks/stop_gate.py",
        "echo x > PYPROJECT.TOML",
        "printf '[[suppression]]' >> suppressions.toml",
        "sed -i 's/a/b/' tools/check_suppressions.py",
        "cp other.py tools/changes.py",
        "rm tools/check_coverage_records.py",
        "printf 'exit 0' > tools/mutation.sh",
        "rm Tools/Check_Declarations.py",
        "cat new.toml | tee ruff.toml",
        "mv /tmp/x .github/workflows/ci.yml",
        "cp other.cfg setup.cfg",
        "rm .claude/settings.json",
        "git checkout -- pyproject.toml",
        "git restore tools/check_declarations.py",
    ],
)
def test_bash_command_that_changes_a_gate_asks(command: str) -> None:
    assert asks("Bash", {"command": command})


@pytest.mark.parametrize(
    "command",
    ["Set-Content pyproject.toml 'x'", "Remove-Item .coveragerc", "'x' | Out-File mypy.ini", "uv add requests"],
)
def test_powershell_command_that_changes_a_gate_asks(command: str) -> None:
    assert asks("PowerShell", {"command": command})


@pytest.mark.parametrize(
    "command",
    [
        "cat pyproject.toml",
        "grep -n ruff pyproject.toml 2>/dev/null",
        "uv sync --all-groups",
        "uv lock",
        "uv run pytest > out.txt",
        "sed -n 1,20p pyproject.toml",
        "git diff pyproject.toml",
        "rm build/output.txt",
    ],
)
def test_bash_command_that_only_reads_is_silent(command: str) -> None:
    assert decide("Bash", {"command": command}) is None


def test_other_tool_is_silent() -> None:
    assert decide("Read", {"file_path": "/repo/pyproject.toml"}) is None


def test_runs_as_script(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    event: str = json.dumps({"tool_name": "Write", "tool_input": {"file_path": "pyproject.toml"}})
    monkeypatch.setattr(sys, "stdin", io.StringIO(event))
    exit_info: pytest.ExceptionInfo[SystemExit]
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_path(str(GUARD), run_name="__main__")
    assert exit_info.value.code == 0
    assert '"permissionDecision": "ask"' in capsys.readouterr().out
