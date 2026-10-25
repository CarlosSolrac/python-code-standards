"""Copy each vendored file into its heredoc in the setup script.

``setup-standards.sh`` embeds the skill's templates and tools so it runs on a host
with no clone of this repo; ``tests/test_setup_script.py`` fails when a copy has
drifted from its source. Renovate runs this after bumping a template's versions.

Run it after changing any vendored file, then ``skill.tools.template_history``.

Usage (from the directory holding ``pyproject.toml``):
    uv run python -m skill.tools.vendor_templates
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from pathlib import Path

SCRIPT: Path = Path("skill/assets/setup-standards.sh")

SOURCES: dict[str, Path] = {
    "PYEOF": Path("skill/tools/check_declarations.py"),
    "TOML": Path("skill/assets/pyproject-baseline.toml"),
    "YAML": Path("skill/assets/pre-commit-config.yaml"),
    "ATTR": Path("skill/assets/gitattributes"),
    "CI": Path("skill/assets/ci.yml"),
    "GUARDEOF": Path("skill/tools/hooks/guard_protected.py"),
    "STOPEOF": Path("skill/tools/hooks/stop_gate.py"),
    "HOOKSINIT": Path("skill/tools/hooks/__init__.py"),
    "SETTINGS": Path("skill/assets/claude-settings.json"),
    "CHANGESEOF": Path("skill/tools/changes.py"),
    "SUPPRESSEOF": Path("skill/tools/check_suppressions.py"),
    "COVRECEOF": Path("skill/tools/check_coverage_records.py"),
    "ALLOWEOF": Path("skill/assets/suppressions.toml"),
    "MUTEOF": Path("skill/tools/mutation.sh"),
    "MUTCI": Path("skill/assets/mutation.yml"),
    "BRIEFEOF": Path("skill/tools/review_brief.py"),
    "SETUPEOF": Path("skill/tools/setup_files.py"),
}
"""The file each heredoc delimiter vendors, as ``tests/test_setup_script.py`` checks them."""


def main(argv: list[str] | None = None, script: Path = SCRIPT, sources: Mapping[str, Path] = SOURCES) -> int:
    """Copy every vendored file into the setup script.

    Args:
        argv: Command-line arguments, defaulting to ``sys.argv[1:]``.
        script: The setup script to read and update.
        sources: The file each heredoc delimiter vendors.

    Returns:
        0; a missing heredoc raises ``ValueError``.
    """
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args(argv)
    current: str = script.read_text(encoding="utf-8")
    updated: str = vendor(current, {delimiter: path.read_text(encoding="utf-8") for delimiter, path in sources.items()})
    if updated == current:
        print(f"{script} is up to date")
        return 0
    script.write_text(updated, encoding="utf-8", newline="")
    print(f"updated {script}")
    return 0


def vendor(script: str, bodies: Mapping[str, str]) -> str:
    """Return the script with the first heredoc of each delimiter holding the given body.

    Raises:
        ValueError: The script has no heredoc for one of the delimiters.
    """
    delimiter: str
    body: str
    for delimiter, body in bodies.items():
        opener: str = f"<<'{delimiter}'"
        if opener not in script:
            message: str = f"no heredoc {opener} in the setup script"
            raise ValueError(message)
        start: int = script.index("\n", script.index(opener)) + 1
        # Only a line that is exactly the delimiter closes a heredoc in bash.
        end: int = script.index(f"\n{delimiter}\n", start - 1) + 1
        script = script[:start] + body + script[end:]
    return script


if __name__ == "__main__":
    raise SystemExit(main())
