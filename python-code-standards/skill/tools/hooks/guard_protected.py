"""PreToolUse hook: ask the user before a tool call changes a quality gate.

Tool configuration, the pre-commit and CI pipelines, the gate scripts, and the
hook settings decide what "passing" means. An agent that edits them can make a
failing check pass without fixing anything, so each such edit needs the user's
explicit approval. The hook answers "ask" rather than "deny": a legitimate
change is one approval away, an illegitimate one is never silent.

Shell commands are matched by pattern, so the shell check is best effort; CI,
which runs the unmodified gates, remains the backstop.

Usage, from ``.claude/settings.json``, with the hook event JSON on stdin. It runs
in the project environment, whatever the current directory:
    uv run --no-sync --project "$CLAUDE_PROJECT_DIR" python "$CLAUDE_PROJECT_DIR/tools/hooks/guard_protected.py"
Exit status is always 0; the decision is the JSON written to stdout.
"""

from __future__ import annotations

import json
import re
import sys
from typing import TextIO, cast

PROTECTED_NAMES: frozenset[str] = frozenset(
    {
        "pyproject.toml",
        "ruff.toml",
        ".ruff.toml",
        "setup.cfg",
        "mypy.ini",
        "pyrightconfig.json",
        "pytest.ini",
        "tox.ini",
        ".coveragerc",
        ".pre-commit-config.yaml",
        "suppressions.toml",
    }
)
PROTECTED_SUFFIXES: tuple[str, ...] = (
    "/tools/check_declarations.py",
    "/tools/check_suppressions.py",
    "/tools/check_coverage_records.py",
    "/tools/changes.py",
    "/tools/mutation.sh",
    "/tools/review_brief.py",
    "/.claude/settings.json",
    "/.claude/settings.local.json",
)
PROTECTED_DIRECTORIES: tuple[str, ...] = ("/.github/workflows/", "/tools/hooks/")
FILE_TOOLS: frozenset[str] = frozenset({"edit", "write", "multiedit", "apply_patch"})
SHELL_TOOLS: frozenset[str] = frozenset({"bash", "powershell"})
PATH_KEYS: frozenset[str] = frozenset({"file_path", "filepath", "path"})
PATCH_FILE_HEADER: re.Pattern[str] = re.compile(r"^\*\*\* (?:(?:Add|Update|Delete) File|Move to):[ \t]*(.+?)[ \t]*\r?$", re.MULTILINE)

# Every protected file as it can appear in a command. One alternation serves both
# patterns below, so a redirect is checked against exactly the files that are named.
PROTECTED_TARGETS: str = (
    "(?:"
    + "|".join(re.escape(name) for name in sorted(PROTECTED_NAMES))
    + r"|\.github[/\\]workflows|tools[/\\](?:check_declarations|check_suppressions|check_coverage_records|changes|review_brief)\.py|tools[/\\]mutation\.sh|tools[/\\]hooks|\.claude[/\\]settings)"
)
# A protected file named anywhere in a command: a bare name, or a path ending in one.
PROTECTED_IN_COMMAND: re.Pattern[str] = re.compile(r"(?:^|[\s'\"=/\\])" + PROTECTED_TARGETS, re.IGNORECASE)
# Commands that write, move, or delete the files they name. A redirect only
# counts when it targets a protected file, so "2>/dev/null" stays silent.
WRITES_IN_COMMAND: re.Pattern[str] = re.compile(
    r"\bsed\b[^|;&\n]*\s(?:-[a-zA-Z]*i|--in-place)"
    r"|>>?\s*['\"]?[^\s|;&]*" + PROTECTED_TARGETS + r"|\b(?:tee|mv|cp|rm|truncate)\b"
    r"|\bgit\s+(?:checkout|restore)\b"
    r"|\b(?:Set-Content|Add-Content|Out-File|Remove-Item|Move-Item|Copy-Item)\b",
    re.IGNORECASE,
)
DEPENDENCY_CHANGE: re.Pattern[str] = re.compile(r"\buv\s+(?:add|remove)\b|\buv\s+lock\b[^|;&\n]*--upgrade")


def main(stdin: TextIO = sys.stdin, stdout: TextIO = sys.stdout) -> int:
    """Read one PreToolUse event and write an "ask" decision when it changes a gate.

    Args:
        stdin: Source of the hook event JSON.
        stdout: Destination of the decision JSON; nothing is written to allow the call.

    Returns:
        Always 0, so the hook consumer reads the decision from stdout.
    """
    event: dict[str, object] = json.loads(stdin.read())
    tool_input: object = event.get("tool_input", {})
    reason: str | None = protected_reason(str(event.get("tool_name", "")), tool_input)
    if reason is not None:
        copilot_compatible_event: bool = event.get("hook_event_name") == "PreToolUse" and isinstance(event.get("timestamp"), str) and "tool_use_id" not in event
        decision: dict[str, object]
        if copilot_compatible_event:
            decision = {"permissionDecision": "ask", "permissionDecisionReason": reason}
        else:
            decision = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask", "permissionDecisionReason": reason}}
        stdout.write(json.dumps(decision))
    return 0


def protected_reason(tool_name: str, tool_input: object) -> str | None:
    """Return why this tool call needs the user's approval, or None when it does not."""
    name: str = tool_name.casefold()
    if name not in FILE_TOOLS and name not in SHELL_TOOLS:
        return None
    decoded_input: object = decode_input(tool_input)
    if not isinstance(decoded_input, (dict, str)):
        return "This tool input could not be inspected for quality-gate changes, so the user must approve it."
    if name in FILE_TOOLS:
        return file_tool_reason(name, decoded_input)
    return shell_tool_reason(decoded_input)


def file_tool_reason(tool_name: str, tool_input: dict[object, object] | str) -> str | None:
    """Return why a file-tool input needs approval, or None when its targets are ordinary files."""
    if tool_name != "apply_patch" and isinstance(tool_input, str):
        return "This file tool input could not be inspected for quality-gate changes, so the user must approve it."
    if isinstance(tool_input, dict) and has_invalid_path(tool_input):
        return "This file tool input could not be inspected for quality-gate changes, so the user must approve it."
    paths: list[str] = target_paths(tool_input)
    if not paths:
        return "This file tool input could not be inspected for quality-gate changes, so the user must approve it."
    path: str
    for path in paths:
        if is_protected(path):
            return f"{path} defines a quality gate. Changing it can make a failing check pass without a fix, so the user must approve. If the goal is a passing check, fix the code instead."
    return None


def shell_tool_reason(tool_input: dict[object, object] | str) -> str | None:
    """Return why a shell-tool input needs approval, or None when its command is safe."""
    if isinstance(tool_input, dict) and "command" not in tool_input:
        return "This shell command could not be inspected for quality-gate changes, so the user must approve it."
    command: object = tool_input.get("command", "") if isinstance(tool_input, dict) else tool_input
    if not isinstance(command, str):
        return "This shell command could not be inspected for quality-gate changes, so the user must approve it."
    return command_reason(command)


def decode_input(tool_input: object) -> object:
    """Parse JSON-encoded tool objects while preserving raw patch and command strings."""
    if isinstance(tool_input, str) and tool_input.lstrip().startswith(("{", "[")):
        try:
            decoded: object = cast("object", json.loads(tool_input))
        except json.JSONDecodeError:
            return tool_input
        else:
            return decoded
    return tool_input


def target_paths(tool_input: object) -> list[str]:
    """Return recognized paths from structured tool inputs or file headers in a raw patch."""
    if isinstance(tool_input, str):
        return [match.group(1).strip() for match in PATCH_FILE_HEADER.finditer(tool_input)]
    paths: list[str] = []
    if isinstance(tool_input, dict):
        key: object
        value: object
        for key, value in cast("dict[object, object]", tool_input).items():
            if isinstance(key, str) and key.casefold() in PATH_KEYS and isinstance(value, str):
                paths.append(value)
            elif isinstance(value, (dict, list)):
                paths.extend(target_paths(value))
    elif isinstance(tool_input, list):
        item: object
        for item in cast("list[object]", tool_input):
            paths.extend(target_paths(item))
    return paths


def has_invalid_path(tool_input: object) -> bool:
    """Return whether a recognized path key has a value the hook cannot inspect."""
    if isinstance(tool_input, dict):
        key: object
        value: object
        for key, value in cast("dict[object, object]", tool_input).items():
            if isinstance(key, str) and key.casefold() in PATH_KEYS:
                if not isinstance(value, str) or not value.strip():
                    return True
            elif isinstance(value, (dict, list)) and has_invalid_path(value):
                return True
    elif isinstance(tool_input, list):
        item: object
        for item in cast("list[object]", tool_input):
            if has_invalid_path(item):
                return True
    return False


def is_protected(path: str) -> bool:
    """Return whether a file path, POSIX or Windows, names a protected file.

    Matching ignores case: on Windows and macOS ``PyProject.toml`` *is* the
    protected file. On a case-sensitive filesystem the cost is an extra prompt.
    """
    # The leading "/" anchors the suffix and directory checks for a relative path.
    normalized: str = "/" + path.replace("\\", "/").casefold()
    name: str = normalized.rpartition("/")[2]
    return name in PROTECTED_NAMES or normalized.endswith(PROTECTED_SUFFIXES) or any(directory in normalized for directory in PROTECTED_DIRECTORIES)


def command_reason(command: str) -> str | None:
    """Return why a shell command needs the user's approval, or None when it does not."""
    if DEPENDENCY_CHANGE.search(command):
        return "This command changes the project's dependencies, which needs the user's approval. Ask before adding, removing, or upgrading a package."
    if PROTECTED_IN_COMMAND.search(command) and WRITES_IN_COMMAND.search(command):
        return "This command appears to modify a file that defines a quality gate, which needs the user's approval. If the goal is a passing check, fix the code instead."
    return None


if __name__ == "__main__":
    raise SystemExit(main())
