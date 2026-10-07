"""Install the setup script's staged templates into a repository without silently losing edits.

The setup script stages every template in a directory, then runs this module from
the repository root. Each existing file is compared with its template:

- current: identical to the template (line endings aside); nothing to do.
- outdated: an earlier standards version nobody edited, recognized by its digest
  in the setup script's history. Replacing it loses nothing, so an interactive run
  offers it after one confirmation, and ``--yes --update`` replaces it unasked.
- edited: anything else. Kept, unless ``--force`` replaces it after saving
  ``<file>.orig``; an interactive run confirms that separately.

Missing files are created. ``pyproject.toml`` is edited by every project (``uv add``
alone changes it), so it is compared table by table instead: each ``[tool.*]``
table of the baseline goes through the same states, and a table that is replaced
is swapped in place, leaving every other line as it was. The file is saved as
``pyproject.toml.orig`` before any swap, since comments inside a table do not
change its parsed value and would otherwise be lost unseen. Tables the baseline does
not define, such as ``[tool.check-declarations]``, are never touched.
``[dependency-groups]`` is only reported: development tools the project lacks are
listed, never added.

The module runs standalone in the target repository, so it uses the standard
library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import tomllib
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

PYPROJECT: str = "pyproject.toml"
SETTINGS: str = ".claude/settings.json"
HEADER: re.Pattern[str] = re.compile(r"^\[\[?([^\[\]]+)\]\]?\s*(?:#.*)?$")
"""A TOML table or array-of-tables header line; group 1 is its dotted key."""

REQUIREMENT_END: re.Pattern[str] = re.compile(r"[\s<>=!~;\[(@]")
"""Where a requirement's project name ends: at a version, marker, extra, or URL."""


class Status(StrEnum):
    """How an existing file or table compares with its template."""

    MISSING = "missing"
    CURRENT = "current"
    OUTDATED = "outdated"
    EDITED = "edited"


class RewriteError(Exception):
    """A table could not be swapped in place, so ``pyproject.toml`` needs a manual merge."""


@dataclass(frozen=True)
class Item:
    """One file, or one ``[tool.*]`` table of ``pyproject.toml``, and its status."""

    path: str
    status: Status
    table: str = ""

    def label(self) -> str:
        """Return the file path, followed by the table for a ``pyproject.toml`` table."""
        return f"{self.path} [tool.{self.table}]" if self.table else self.path


def main(argv: list[str] | None = None, ask: Callable[[str], str] = input) -> int:
    """Install the staged templates into the current directory.

    Args:
        argv: Command-line arguments, defaulting to ``sys.argv[1:]``.
        ask: Prompts the user and returns the reply; raises ``EOFError`` without one.

    Returns:
        0; a failure raises.
    """
    parser: argparse.ArgumentParser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("stage", type=Path, help="directory holding the templates, laid out as in the repository")
    parser.add_argument("--hashes", type=Path, required=True, help="JSON digests of every earlier template version")
    parser.add_argument("--yes", action="store_true", help="never ask; replace only what --update or --force allows")
    parser.add_argument("--update", action="store_true", help="with --yes, replace unedited earlier versions")
    parser.add_argument("--force", action="store_true", help="like --update, and also replace edited files and tables, saving <file>.orig first")
    args: argparse.Namespace = parser.parse_args(argv)

    history: dict[str, dict[str, list[str]]] = json.loads(args.hashes.read_text(encoding="utf-8"))
    templates: dict[str, str] = staged_templates(args.stage)
    items: list[Item] = survey(templates, history)
    report_items(items)
    chosen: list[Item] = choose(items, assume_yes=args.yes, update=args.update, force=args.force, ask=ask)
    backups: list[Path] = install(items, chosen, templates)
    if backups:
        print(f"\nBacked up: {', '.join(path.as_posix() for path in backups)}. Compare each with its file, then delete it; setup does not stage backups.")
    report_kept(items, chosen, force=args.force)
    report_dev_tools(templates)
    return 0


def staged_templates(stage: Path) -> dict[str, str]:
    """Return each staged template's text, keyed by its path relative to the repository root."""
    return {path.relative_to(stage).as_posix(): path.read_text(encoding="utf-8") for path in sorted(stage.rglob("*")) if path.is_file()}


def survey(templates: Mapping[str, str], history: Mapping[str, Mapping[str, list[str]]]) -> list[Item]:
    """Compare every template with the repository: files whole, an existing ``pyproject.toml`` by table."""
    items: list[Item] = []
    path: str
    template: str
    for path, template in templates.items():
        current: str | None = read(Path(path))
        if path == PYPROJECT and current is not None:
            items.extend(table_items(current, template, history["tables"]))
        else:
            items.append(Item(path, file_status(current, template, history["files"].get(path, []))))
    return items


def read(path: Path) -> str | None:
    """Return a file's text, or None when it does not exist; undecodable bytes count as edits."""
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else None


def table_items(project: str, baseline: str, history: Mapping[str, list[str]]) -> list[Item]:
    """Return one item for each ``[tool.*]`` table the baseline defines."""
    current: dict[str, Any] = tomllib.loads(project).get("tool", {})
    return [Item(PYPROJECT, table_status(current.get(name), template, history.get(f"tool.{name}", [])), name) for name, template in tomllib.loads(baseline)["tool"].items()]


def digest(text: str) -> str:
    """Return the SHA-256 of a text with CRLF line endings normalized, so a Windows checkout matches."""
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def table_digest(value: object) -> str:
    """Return the SHA-256 of a parsed TOML table, independent of how it is formatted."""
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode("utf-8")).hexdigest()


def file_status(current: str | None, template: str, known: Collection[str]) -> Status:
    """Classify a file's text against its template and the digests of earlier versions."""
    if current is None:
        return Status.MISSING
    found: str = digest(current)
    if found == digest(template):
        return Status.CURRENT
    return Status.OUTDATED if found in known else Status.EDITED


def table_status(current: object, template: object, known: Collection[str]) -> Status:
    """Classify a parsed table against the baseline's and the digests of earlier versions."""
    if current is None:
        return Status.MISSING
    if current == template:
        return Status.CURRENT
    return Status.OUTDATED if table_digest(current) in known else Status.EDITED


NOTES: dict[tuple[Status, bool], str] = {
    (Status.MISSING, False): "",
    (Status.MISSING, True): " (--update adds it)",
    (Status.CURRENT, False): "",
    (Status.CURRENT, True): "",
    (Status.OUTDATED, False): " (unedited older version; --update replaces it)",
    (Status.OUTDATED, True): " (unedited older version; --update replaces it)",
    (Status.EDITED, False): " (--force replaces it)",
    (Status.EDITED, True): " (--force replaces it)",
}
"""What each status means for a file, and for a table (True)."""


def report_items(items: list[Item]) -> None:
    """Print one line per file or table: what it is, and what the flags would do with it."""
    item: Item
    for item in items:
        word: str = "create" if item.status is Status.MISSING and not item.table else item.status.value
        print(f"  {word:<8} {item.label()}{NOTES[item.status, bool(item.table)]}")


def safe(item: Item) -> bool:
    """Return whether replacing an item loses nothing: an unedited earlier version, or a table the project lacks."""
    return item.status is Status.OUTDATED or (item.status is Status.MISSING and bool(item.table))


def choose(items: list[Item], *, assume_yes: bool, update: bool, force: bool, ask: Callable[[str], str]) -> list[Item]:
    """Return the existing files and tables to replace, asking first unless ``assume_yes``; ``force`` implies ``update``."""
    unedited: list[Item] = [item for item in items if safe(item)]
    edited: list[Item] = [item for item in items if item.status is Status.EDITED]
    chosen: list[Item] = []
    if unedited and ((update or force) if assume_yes else confirm(f"Replace the {len(unedited)} unedited item(s) above with the current version? [y/N] ", ask)):
        chosen.extend(unedited)
    if edited and force and (assume_yes or confirm(f"Replace the {len(edited)} EDITED item(s) above? Each file is saved as <name>.orig first. [y/N] ", ask)):
        chosen.extend(edited)
    return chosen


def confirm(question: str, ask: Callable[[str], str]) -> bool:
    """Return whether the user answered yes; no answer at all means no."""
    try:
        reply: str = ask(question)
    except EOFError:
        return False
    return reply.strip().lower() in {"y", "yes"}


def install(items: list[Item], chosen: list[Item], templates: Mapping[str, str]) -> list[Path]:
    """Create missing files, and replace the chosen files and tables, backing up edited ones.

    Returns:
        The backups made.
    """
    backups: list[Path] = []
    item: Item
    for item in items:
        if not item.table and (item.status is Status.MISSING or item in chosen):
            backups.extend(write(Path(item.path), templates[item.path], backup_first=item.status is Status.EDITED))
    tables: list[Item] = [item for item in chosen if item.table]
    if tables:
        backups.extend(install_tables(tables, templates[PYPROJECT]))
    return backups


def write(path: Path, text: str, *, backup_first: bool) -> list[Path]:
    """Write a template's text exactly, after saving the file it replaces when that was edited.

    Returns:
        The backup made, if any.
    """
    backups: list[Path] = []
    if backup_first:
        backups.append(backup(path))
        print(f"  backup   {path.as_posix()} -> {backups[0].as_posix()}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="")
    print(f"  {'write':<8} {path.as_posix()}")
    return backups


def install_tables(tables: list[Item], baseline: str) -> list[Path]:
    """Swap the chosen tables into ``pyproject.toml`` after backing it up, or leave it whole when that is not safe.

    Returns:
        The backup made, if any.
    """
    path: Path = Path(PYPROJECT)
    names: list[str] = [item.table for item in tables]
    try:
        text: str = rewrite_tables(path.read_text(encoding="utf-8"), baseline, set(names))
    except RewriteError:
        print(f"{PYPROJECT}: could not rewrite {', '.join(f'[tool.{name}]' for name in names)} in place; merge by hand")
        return []
    # Always backed up: a comment the user added inside an unedited table does not
    # change its parsed value, so the swap would otherwise lose it silently.
    return write(path, text, backup_first=True)


def backup(path: Path) -> Path:
    """Copy a file to the first free ``<name>.orig``, ``<name>.orig.1``, ... and return that path."""
    target: Path = path.with_name(f"{path.name}.orig")
    number: int = 0
    while target.exists():
        number += 1
        target = path.with_name(f"{path.name}.orig.{number}")
    shutil.copy2(path, target)
    return target


def rewrite_tables(text: str, baseline: str, names: Collection[str]) -> str:
    """Return a ``pyproject.toml`` text with each named ``[tool.*]`` table replaced by the baseline's.

    A table's subtables go with it, and a table split across the file is gathered
    where it first appears. A table the text lacks is appended. Every other line is
    kept as it is.

    Raises:
        RewriteError: The result does not parse to the original with exactly those
            tables replaced, as when a table is defined by dotted keys or inline.
    """
    groups: dict[str, str] = {}
    key: str | None
    block: str
    for key, block in blocks(baseline):
        owner: str = tool_name(key)
        if owner in names:
            groups[owner] = groups.get(owner, "") + block
    kept: list[str] = []
    placed: set[str] = set()
    for key, block in blocks(text):
        owner = tool_name(key)
        if owner not in names:
            kept.append(block)
        elif owner not in placed:
            kept.append(groups[owner].rstrip("\n") + "\n\n")
            placed.add(owner)
    name: str
    for name in groups:
        if name not in placed:
            kept.append("\n" if not "".join(kept).endswith("\n\n") else "")
            kept.append(groups[name].rstrip("\n") + "\n\n")
    result: str = "".join(kept).rstrip("\n") + "\n"
    verify(text, baseline, result, names)
    return result


def blocks(text: str) -> list[tuple[str | None, str]]:
    """Split TOML text into (header key, text) blocks, each running from its header to the next.

    Comment lines just above a header describe that header's table, so they open
    its block rather than close the one before.
    """
    found: list[tuple[str | None, list[str]]] = [(None, [])]
    line: str
    for line in text.splitlines(keepends=True):
        match: re.Match[str] | None = HEADER.match(line)
        if match:
            found.append((match.group(1).replace(" ", ""), [*leading_comments(found[-1][1]), line]))
        else:
            found[-1][1].append(line)
    return [(key, "".join(lines)) for key, lines in found]


def leading_comments(lines: list[str]) -> list[str]:
    """Remove and return the comment lines that end a block, with any blank lines after them."""
    start: int = len(lines)
    while start > 0 and (not lines[start - 1].strip() or lines[start - 1].lstrip().startswith("#")):
        start -= 1
    while start < len(lines) and not lines[start].strip():
        start += 1
    moved: list[str] = lines[start:]
    del lines[start:]
    return moved


def tool_name(key: str | None) -> str:
    """Return ``ruff`` for a ``tool.ruff`` or ``tool.ruff.lint`` header key; "" for anything else."""
    parts: list[str] = (key or "").split(".")
    return parts[1] if len(parts) > 1 and parts[0] == "tool" else ""


def verify(original: str, baseline: str, result: str, names: Collection[str]) -> None:
    """Raise unless the rewritten text parses to the original with only the named tables replaced."""
    expected: dict[str, Any] = tomllib.loads(original)
    tool: dict[str, Any] = expected.setdefault("tool", {})
    replacement: dict[str, Any] = tomllib.loads(baseline)["tool"]
    name: str
    for name in names:
        tool[name] = replacement[name]
    try:
        actual: dict[str, Any] = tomllib.loads(result)
    except tomllib.TOMLDecodeError as exc:
        raise RewriteError from exc
    if actual != expected:
        raise RewriteError


def report_kept(items: list[Item], chosen: list[Item], *, force: bool) -> None:
    """Count the edited files and tables that were kept, and say how to replace them."""
    kept: list[Item] = [item for item in items if item.status is Status.EDITED and item not in chosen]
    if kept:
        advice: str = "" if force else " Re-run with --force to replace them (each file is saved as <name>.orig first), or merge by hand."
        print(f"\nKept {len(kept)} edited item(s).{advice}")
    if any(item.path == SETTINGS for item in kept):
        print(f'{SETTINGS} holds your other settings too: merge its "hooks" block by hand rather than replacing it.')


def report_dev_tools(templates: Mapping[str, str]) -> None:
    """List the baseline's development tools that ``pyproject.toml`` does not install.

    Runs after ``install``, so a staged ``pyproject.toml`` always exists by now.
    """
    if PYPROJECT not in templates:
        return
    missing: list[str] = missing_dev_tools(tomllib.loads(Path(PYPROJECT).read_text(encoding="utf-8")), tomllib.loads(templates[PYPROJECT]))
    if missing:
        print(f"\n{PYPROJECT} [dependency-groups] dev lacks: {', '.join(missing)}")
        print("Add them with 'uv add --dev', or copy them from the baseline.")


def missing_dev_tools(project: Mapping[str, Any], baseline: Mapping[str, Any]) -> list[str]:
    """Return the baseline's dev requirements whose project the project's dev group does not name, groups it includes counted."""
    present: set[str] = {requirement_name(requirement) for requirement in group_requirements(project.get("dependency-groups", {}), "dev", set())}
    return [requirement for requirement in baseline["dependency-groups"]["dev"] if requirement_name(requirement) not in present]


def group_requirements(groups: Mapping[str, Any], name: str, seen: set[str]) -> list[str]:
    """Return a dependency group's requirements, following ``{include-group = ...}`` entries (PEP 735).

    ``seen`` stops a cycle, which uv rejects later but a hand-edited file can hold now.
    """
    if name in seen:
        return []
    seen.add(name)
    found: list[str] = []
    entry: object
    for entry in groups.get(name, []):
        if isinstance(entry, str):
            found.append(entry)
        elif isinstance(entry, dict):
            found.extend(group_requirements(groups, str(entry.get("include-group")), seen))
    return found


def requirement_name(requirement: str) -> str:
    """Return a requirement's normalized project name: ``my-tool`` for ``My_Tool>=1; python_version > '3'``."""
    name: str = REQUIREMENT_END.split(requirement.strip())[0]
    return re.sub(r"[-_.]+", "-", name).lower()


if __name__ == "__main__":
    raise SystemExit(main())
