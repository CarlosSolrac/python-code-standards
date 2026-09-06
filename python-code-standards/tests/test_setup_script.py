"""The setup script embeds the skill's templates; assert the copies have not drifted.

``skill/assets/setup-standards.sh`` is self-contained so it can run on a host with
no clone of this repo. That duplication is only safe if drift fails here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

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
    ],
    ids=["check_declarations", "pyproject", "pre-commit", "gitattributes", "ci"],
)
def test_embedded_template_matches_source(delimiter: str, asset: str) -> None:
    """Each embedded heredoc is identical to the file it vendors.

    The ``pyproject.toml`` heredoc keeps the baseline's ``name = "example-project"``
    and the script rewrites it at run time, so the stored text still matches.
    """
    source: str = (REPO_ROOT / asset).read_text(encoding="utf-8")
    assert heredoc(delimiter) == source
