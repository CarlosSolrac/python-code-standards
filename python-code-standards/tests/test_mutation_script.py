"""The mutation-testing runner keeps its Linux environment out of the shared checkout.

``tools/mutation.sh`` runs under WSL on Windows, against the same folder the
Windows tools use. These tests read its commands; the live run is in WSL.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT: Path = Path(__file__).resolve().parent.parent
MUTATION_SCRIPT: Path = REPO_ROOT / "skill" / "tools" / "mutation.sh"


def commands() -> list[str]:
    """Return the script's executable lines, without comments and blank lines."""
    return [line.strip() for line in MUTATION_SCRIPT.read_text(encoding="utf-8").splitlines() if line.strip() and not line.strip().startswith("#")]


def test_environment_lives_outside_the_checkout_before_any_uv_call() -> None:
    """A uv run in the shared folder would replace the Windows .venv with a Linux one."""
    lines: list[str] = commands()
    first_uv: int = next(index for index, line in enumerate(lines) if line.startswith("uv "))
    exports: list[int] = [index for index, line in enumerate(lines) if line.startswith("export UV_PROJECT_ENVIRONMENT=")]
    assert exports
    assert exports[0] < first_uv
    assert "$HOME/" in lines[exports[0]]


def test_forwards_the_mutant_pattern() -> None:
    """``tools/mutation.sh 'pkg.module*'`` narrows a local run to matching mutants."""
    assert 'uv run --no-sync mutmut run "$@"' in commands()


def test_reports_survivors_and_stats() -> None:
    lines: list[str] = commands()
    assert any("mutmut export-cicd-stats" in line for line in lines)
    assert any("mutmut results" in line and "mutants/survivors.txt" in line for line in lines)


def test_requires_explicit_source_paths_before_running() -> None:
    """The script refuses to guess: mutmut's guess uses the checkout folder's name, which breaks in clones and CI."""
    lines: list[str] = commands()
    check: int = next(index for index, line in enumerate(lines) if "source_paths" in line and "pyproject.toml" in line)
    first_uv: int = next(index for index, line in enumerate(lines) if line.startswith("uv "))
    assert check < first_uv
    assert any(line.startswith("exit 2") for line in lines[check:first_uv])


def test_every_documented_invocation_goes_through_bash() -> None:
    """Setup writes the script without the executable bit, and Windows commits never record one.

    So ``tools/mutation.sh`` run directly fails with "Permission denied"; every
    usage example must say ``bash tools/mutation.sh``.
    """
    docs: Path = REPO_ROOT / "docs" / "quality-gates.md"
    examples: list[str] = [line for line in MUTATION_SCRIPT.read_text(encoding="utf-8").splitlines() if line.startswith("#   ") and "mutation.sh" in line]
    examples += [line for line in docs.read_text(encoding="utf-8").splitlines() if "**Run:**" in line]
    assert examples
    assert all("bash tools/mutation.sh" in line for line in examples), examples


def test_runs_from_the_project_root() -> None:
    """The project root holds pyproject.toml; it is not always the git root."""
    assert any("pyproject.toml" in line and "cd" in line for line in commands())
