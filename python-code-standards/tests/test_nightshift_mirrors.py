"""The Claude Code and Copilot CLI copies of each nightshift skill keep their shared sections in step.

The repository ships ``nightshift/SKILL.md`` and ``prep-nightshift/SKILL.md`` for Claude
Code at its root, and a mirror of each under ``copilot/`` for the GitHub Copilot CLI. The
copies share goals, authority, log format and morning deliverable, and differ only in how
the host keeps the night running, denies prompts and reviews work. No tool derives one
copy from the other, so the mapping below is pinned by hand: per file, the sections both
copies share, and per section the (Claude phrase, Copilot phrase) substitutions that are
today's deliberate host differences. Whitespace is flattened first, so re-wrapping is not
drift. Whoever edits a shared section in one copy edits the other, or re-pins the pair.
"""

from __future__ import annotations

import difflib
import re
from pathlib import Path

import pytest

pytestmark: pytest.MarkDecorator = pytest.mark.no_mutation  # reads files outside the copy mutmut runs in

REPOSITORY: Path = Path(__file__).resolve().parent.parent.parent

type Substitutions = list[tuple[str, str]]

MIRRORS: dict[str, dict[str, Substitutions]] = {
    "nightshift": {
        "Authority": [("Every other rule from CLAUDE.md files and skills", "Every other rule from the user's instruction files and skills")],
        "Plan": [],
        "Close-the-session warning": [("its permission mode was chosen so nothing would stop for you", "it ran in autopilot with every permission allowed, so nothing would stop for you")],
        "Decisions": [("design tradeoffs raised in code review", "design tradeoffs raised in review")],
        "Blockers": [
            (
                'A permission prompt denied with "Unattended: nobody can approve this call" is one: that message comes from the user\'s own hook (*Running it*), so act on it. Log the exact tool call',
                "A tool call denied because the CLI could not ask the user, or denied by a hook, is one: log the exact tool call",
            ),
        ],
        "Log format": [
            ("Status: in progress | waiting for Codex | complete", "Status: in progress | waiting for reviews | complete"),
            ("Session: <id of the session running the night>", "Session: <id of the Copilot session running the night> Host: Copilot CLI"),
            (
                "| Codex reviews | Branch / PR | |---|------|--------|------------|--------|---------------|-------------|",
                "| Reviews | Branch / PR | |---|------|--------|------------|--------|---------|-------------|",
            ),
            ("— job <id> failed <time>:", "— <model> failed <time>:"),
            ("<preflight results: settings, default branch,", "<preflight results: settings, models, hook, default branch,"),
            (
                "Timestamps use local time, read from the clock as each entry is written (`date +%H:%M` for the timeline, `date '+%Y-%m-%d %H:%M'` for the header); never estimate one.",
                "The hook appends permission-prompt lines at the end of the file, which is the *Timeline*.",
            ),
        ],
    },
    "prep-nightshift": {
        "Steps": [],
        "2. Confirm scope": [],
        "3. Find inputs the worktrees would miss": [],
        "4. Flag steps outside the authority": [("(`~/.claude` files,", "(`~/.copilot` or `~/.claude` files,")],
        "5. Settle open decisions": [
            ("recommend one, do not record it.", "recommend one, do not record it. `thorough` runs a six-model deep review per task and costs far more premium requests."),
        ],
        "7. Commit and push after approval": [],
    },
}
"""Per skill directory, the sections both copies share, each with its pinned (Claude phrase, Copilot phrase) host differences."""


def flat(text: str) -> str:
    """Return the text with every run of whitespace as one space, so re-wrapping is not drift."""
    return " ".join(text.split())


def sections(path: Path) -> dict[str, str]:
    """Return the body of each ``##`` or ``###`` section of a Markdown file, keyed by heading.

    Heading-like lines inside fenced blocks belong to the section that holds the fence.
    """
    found: dict[str, list[str]] = {}
    body: list[str] = []
    fenced: bool = False
    line: str
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
        heading: re.Match[str] | None = None if fenced else re.match(r"#{2,3} (.+)$", line)
        if heading:
            body = found.setdefault(heading.group(1), [])
        else:
            body.append(line)
    return {name: "\n".join(lines) for name, lines in found.items()}


def drift(claude: str, copilot: str, substitutions: Substitutions) -> str:
    """Describe how the Copilot section differs from the Claude section once the pinned substitutions are applied.

    Returns:
        An empty string when they match. Otherwise each stale pin (a Claude phrase not found
        exactly once), then a unified diff of the flattened texts split at sentence boundaries.
    """
    expected: str = flat(claude)
    problems: list[str] = []
    old: str
    new: str
    for old, new in substitutions:
        if expected.count(flat(old)) != 1:
            problems.append(f"stale pin, not found exactly once in the Claude copy: {old!r}")
        expected = expected.replace(flat(old), flat(new))
    actual: str = flat(copilot)
    if expected != actual:
        sentences: str = r"(?<=[.:;]) "
        problems.extend(difflib.unified_diff(re.split(sentences, expected), re.split(sentences, actual), "Claude, pins applied", "Copilot", n=0, lineterm=""))
    return "\n".join(problems)


@pytest.mark.parametrize(("skill", "heading"), [pytest.param(skill, heading, id=f"{skill}::{heading}") for skill, shared in MIRRORS.items() for heading in shared])
def test_shared_section_matches_its_mirror(skill: str, heading: str) -> None:
    claude_path: Path = REPOSITORY / skill / "SKILL.md"
    copilot_path: Path = REPOSITORY / "copilot" / skill / "SKILL.md"
    claude: dict[str, str] = sections(claude_path)
    copilot: dict[str, str] = sections(copilot_path)
    pair: str = f"{claude_path.relative_to(REPOSITORY).as_posix()} vs {copilot_path.relative_to(REPOSITORY).as_posix()}"
    assert heading in claude, f"{pair}: section {heading!r} missing from the Claude copy"
    assert heading in copilot, f"{pair}: section {heading!r} missing from the Copilot copy"
    difference: str = drift(claude[heading], copilot[heading], MIRRORS[skill][heading])
    assert not difference, f"{pair}, section {heading!r} drifted:\n{difference}"


def test_a_sentence_added_to_one_copy_is_drift() -> None:
    difference: str = drift("Keep the log.\nUpdate it in place.", "Keep the log. Update it in place. Never append a copy.", [])
    assert "+Never append a copy." in difference
