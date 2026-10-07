"""Record the digest of every template version the setup script has ever written.

``setup_files.py`` replaces an existing file without warning only when the file is,
byte for byte, a template an earlier setup script wrote, so nothing the project
changed is lost. This builds that list from every committed version of the setup
script, plus the working copy, and embeds it in the script's ``HASHEOF`` heredoc.
``pyproject.toml`` is recorded table by table, since projects always edit it.

Run it after changing any template; a test fails until the digests cover them.

Usage (from the directory holding ``pyproject.toml``):
    uv run python -m skill.tools.template_history
"""

from __future__ import annotations

import argparse
import json
import re
import tomllib
from collections.abc import Iterable, Iterator, Mapping
from itertools import takewhile
from pathlib import Path

from .hooks.stop_gate import GitError, Result, Runner, run_command
from .setup_files import PYPROJECT, digest, table_digest

SCRIPT: Path = Path("skill/assets/setup-standards.sh")
WRITER: re.Pattern[str] = re.compile(r"^write_file (\S+) (?:<<'(\w+)'|</dev/null)$")
"""A line that writes one file, from a quoted heredoc or as an empty file."""

TOML_OPENER: str = "<<'TOML'"
"""The heredoc holding the baseline ``pyproject.toml``, written by its own ``sed`` line."""

DELIMITER: str = "HASHEOF"


def main(argv: list[str] | None = None, run: Runner = run_command, script: Path = SCRIPT) -> int:
    """Embed the digests of every template version in the setup script.

    Args:
        argv: Command-line arguments, defaulting to ``sys.argv[1:]``.
        run: Runs git.
        script: The setup script to read and update.

    Returns:
        0; a git failure raises ``GitError``.
    """
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args(argv)
    current: str = script.read_text(encoding="utf-8")
    updated: str = embed(current, known_digests([*script_versions(run, script.as_posix()), current], recorded=embedded(current)))
    if updated == current:
        print(f"{script} is up to date")
        return 0
    script.write_text(updated, encoding="utf-8", newline="")
    print(f"updated {script}")
    return 0


def script_versions(run: Runner, path: str) -> list[str]:
    """Return the text of every committed version of a file, newest first.

    Raises:
        GitError: git failed, so the history would be incomplete.
    """
    command: tuple[str, ...] = ("git", "log", "--format=%H", "--", path)
    result: Result = run(command)
    if result.returncode != 0:
        raise GitError(command, result)
    versions: list[str] = []
    commit: str
    for commit in result.output.split():
        show: tuple[str, ...] = ("git", "show", f"{commit}:./{path}")
        shown: Result = run(show)
        if shown.returncode != 0:
            raise GitError(show, shown)
        versions.append(shown.output)
    return versions


def known_digests(scripts: Iterable[str], recorded: Mapping[str, Mapping[str, list[str]]]) -> dict[str, dict[str, list[str]]]:
    """Return the recorded digests plus those of every file and ``[tool.*]`` table any of the scripts writes.

    Digests are only ever added: a shallow clone sees little history, and dropping
    what it cannot see would make unedited files from older versions look edited.
    """
    files: dict[str, set[str]] = {path: set(digests) for path, digests in recorded.get("files", {}).items()}
    tables: dict[str, set[str]] = {table: set(digests) for table, digests in recorded.get("tables", {}).items()}
    script: str
    for script in scripts:
        path: str
        text: str
        for path, text in templates(script).items():
            if path == PYPROJECT:
                name: str
                value: object
                for name, value in tomllib.loads(text).get("tool", {}).items():
                    tables.setdefault(f"tool.{name}", set()).add(table_digest(value))
            else:
                files.setdefault(path, set()).add(digest(text))
    return {"files": _sorted(files), "tables": _sorted(tables)}


def _sorted(digests: Mapping[str, set[str]]) -> dict[str, list[str]]:
    """Return the digests in a stable order, so regenerating changes nothing."""
    return {key: sorted(digests[key]) for key in sorted(digests)}


def templates(script: str) -> dict[str, str]:
    """Return the text of each file a setup script writes, keyed by its path in the repository."""
    found: dict[str, str] = {}
    lines: Iterator[str] = iter(script.splitlines(keepends=True))
    line: str
    for line in lines:
        # bash ignores trailing blanks on the command line, but not on the closing delimiter line.
        opener: tuple[str, str | None] | None = _opener(line.rstrip())
        if opener is None:
            continue
        path: str = opener[0]
        delimiter: str | None = opener[1]
        found[path] = "" if delimiter is None else _heredoc_body(lines, delimiter)
    return found


def _heredoc_body(lines: Iterator[str], delimiter: str) -> str:
    """Consume and return a heredoc's lines, up to and including its closing delimiter line."""
    return "".join(takewhile(lambda body: body.rstrip("\n") != delimiter, lines))


def _opener(line: str) -> tuple[str, str | None] | None:
    """Return the path and heredoc delimiter a line starts writing, or None for any other line."""
    if line.endswith(TOML_OPENER):
        return PYPROJECT, "TOML"
    match: re.Match[str] | None = WRITER.match(line)
    return (match.group(1), match.group(2)) if match else None


def embed(script: str, digests: Mapping[str, Mapping[str, list[str]]]) -> str:
    """Return the script with its ``HASHEOF`` heredoc holding the digests as JSON, in their given order."""
    start: int
    end: int
    start, end = _digest_span(script)
    return script[:start] + json.dumps(digests, indent=1) + "\n" + script[end:]


def embedded(script: str) -> dict[str, dict[str, list[str]]]:
    """Return the digests the script's ``HASHEOF`` heredoc holds."""
    start: int
    end: int
    start, end = _digest_span(script)
    digests: dict[str, dict[str, list[str]]] = json.loads(script[start:end])
    return digests


def _digest_span(script: str) -> tuple[int, int]:
    """Return where the ``HASHEOF`` heredoc's body starts and ends in the script."""
    opener: str = f"<<'{DELIMITER}'\n"
    start: int = script.index(opener) + len(opener)
    return start, script.index(f"\n{DELIMITER}\n", start - 1) + 1


if __name__ == "__main__":
    raise SystemExit(main())
