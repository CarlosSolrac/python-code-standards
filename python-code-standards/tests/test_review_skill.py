"""The review skill carries no coding how-to, and its invariants stay tied to where the gates are documented.

``review-standards/SKILL.md`` sits at the repository root, beside this project. Its
invariants are prose a reviewer checks, and no tool derives them from the gate
documentation, so the mapping below is pinned by hand: each invariant names a phrase
of its own text and a phrase that must stand in the document stating that rule.
Rewording either side fails here, and whoever changes it re-pins the pair.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark: pytest.MarkDecorator = pytest.mark.no_mutation  # reads files outside the copy mutmut runs in

PROJECT: Path = Path(__file__).resolve().parent.parent
REPOSITORY: Path = PROJECT.parent
REVIEW_SKILL: Path = REPOSITORY / "review-standards" / "SKILL.md"
GATES: Path = PROJECT / "docs" / "quality-gates.md"
PROTOCOL: Path = REPOSITORY / "CLAUDE.md"

INVARIANTS: list[tuple[str, Path, str]] = [
    ("Every changed line is covered by a test", GATES, "`diff-cover --fail-under=100` against `main`"),
    ("No new suppression", GATES, 'Makes "suppressions need approval" mechanical.'),
    ("No change to CI, hooks, or build configuration", GATES, 'This hook asks the user before a tool call changes anything that decides what "passing" means'),
    ("No dependency added, removed or upgraded", GATES, "It also asks on `uv add`, `uv remove`, and `uv lock --upgrade`."),
    # No gate checks this one; the review protocol in the repository's CLAUDE.md states it.
    ("A bug fix includes a regression test", PROTOCOL, "Add a regression test for each fix"),
]
"""Per invariant, in the skill's order: a phrase of its text, the document stating the rule, and the phrase stating it there."""


def flat(text: str) -> str:
    """Return the text with every run of whitespace as one space, so a phrase matches across wrapped lines."""
    return re.sub(r"\s+", " ", text)


def invariants() -> list[str]:
    """Return the numbered items under the skill's "Project invariants to check" heading."""
    section: str = REVIEW_SKILL.read_text(encoding="utf-8").split("## Project invariants to check", 1)[1].split("\n## ", 1)[0]
    return re.findall(r"^\d+\. (.+)$", section, re.MULTILINE)


def test_each_invariant_is_pinned_to_the_rule_it_restates() -> None:
    stated: list[str] = invariants()
    assert len(stated) == len(INVARIANTS)
    item: str
    own: str
    document: Path
    phrase: str
    for item, (own, document, phrase) in zip(stated, INVARIANTS, strict=True):
        assert own in item
        assert flat(phrase) in flat(document.read_text(encoding="utf-8")), (document.name, phrase)


def test_the_review_skill_names_no_coding_guide_file() -> None:
    """NFR-13: the reviewer is pointed at no part of the coding skill, so nothing in it leads the reviewer to the writer's guide."""
    text: str = REVIEW_SKILL.read_text(encoding="utf-8")
    guide: list[str] = ["python-code-standards", "references/", "conformance.py", "SKILL.md", *(path.name for path in (PROJECT / "skill" / "references").iterdir())]
    assert [name for name in guide if name in text] == []


def test_the_review_skill_is_one_file() -> None:
    """NFR-13: it has no references of its own, so none can be shared with the coding skill."""
    assert [path.name for path in REVIEW_SKILL.parent.iterdir()] == ["SKILL.md"]
