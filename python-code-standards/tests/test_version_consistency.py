"""Every copy of a tool's version agrees, so CI fails when one copy is bumped alone.

Renovate keeps these aligned by updating all of a package's files in one pull
request, but nothing else does: a hand edit, or a ``packageRules`` change that
splits a group, would otherwise pass CI with the copies disagreeing.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Mapping
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

REPO_ROOT: Path = Path(__file__).resolve().parent.parent
ASSETS: Path = REPO_ROOT / "skill" / "assets"

RUFF_HOOK: re.Pattern[str] = re.compile(r"^\s*- repo: https://github\.com/astral-sh/ruff-pre-commit\n\s*rev: v(?P<version>\S+)$", re.MULTILINE)
USES: re.Pattern[str] = re.compile(r"^\s*(?:- )?uses: (?P<target>.+?)\s*$", re.MULTILINE)
ACTION_PIN: re.Pattern[str] = re.compile(r"(?P<action>[\w.-]+/[\w.-]+)@(?P<pin>[0-9a-f]{40} # v\S+)")


def dev_requirements(pyproject: str) -> dict[str, Requirement]:
    """Return the ``[dependency-groups] dev`` entries of a ``pyproject.toml``, keyed by normalized name.

    Raises:
        KeyError: The file has no dev group, so a renamed table fails instead of comparing nothing.
    """
    return {canonicalize_name(requirement.name): requirement for requirement in map(Requirement, tomllib.loads(pyproject)["dependency-groups"]["dev"])}


def dev_requirement_mismatches(repo: str, baseline: str) -> list[str]:
    """Return each baseline dev entry the repository omits or declares with another range, marker, or extra.

    Entries only the repository declares are its own tooling and are not compared.
    """
    declared: dict[str, Requirement] = dev_requirements(repo)
    return [f"{name}: baseline {wanted}, repository {declared.get(name)}" for name, wanted in dev_requirements(baseline).items() if declared.get(name) != wanted]


def ruff_hook_mismatches(baseline: str, pre_commit: str) -> list[str]:
    """Return why the ``ruff-pre-commit`` hook does not pin the baseline's minimum Ruff, if it does not."""
    hook: re.Match[str] | None = RUFF_HOOK.search(pre_commit)
    if hook is None:
        return ["no ruff-pre-commit rev in the pre-commit config"]
    minimum: list[str] = [specifier.version for specifier in dev_requirements(baseline)["ruff"].specifier if specifier.operator == ">="]
    return [] if minimum == [hook["version"]] else [f"ruff-pre-commit rev v{hook['version']}, baseline minimum {minimum}"]


def workflow_files(*folders: Path) -> list[Path]:
    """Return the YAML files in each folder, since GitHub runs both ``.yml`` and ``.yaml`` workflows."""
    return sorted(path for folder in folders for path in folder.iterdir() if path.suffix in {".yml", ".yaml"})


def action_pin_mismatches(workflows: Mapping[str, str]) -> list[str]:
    """Return each ``uses:`` line not pinned to a SHA with a version comment, and each action with more than one pin.

    Args:
        workflows: Workflow text keyed by the name each problem is reported under.
    """
    problems: list[str] = []
    pins: dict[str, set[str]] = {}
    name: str
    text: str
    for name, text in workflows.items():
        target: str
        for target in USES.findall(text):
            pinned: re.Match[str] | None = ACTION_PIN.fullmatch(target)
            if pinned is None:
                problems.append(f"{name}: {target} is not pinned to a SHA with a version comment")
            else:
                pins.setdefault(pinned["action"], set()).add(pinned["pin"])
    if not pins:
        problems.append("no pinned actions in the workflows")
    problems.extend(f"{action}: {' | '.join(sorted(found))}" for action, found in sorted(pins.items()) if len(found) > 1)
    return problems


BASELINE: str = '[dependency-groups]\ndev = [\n    "mypy>=2.4,<3",\n    "ruff>=0.17.2,<0.18",\n]\n'
PRE_COMMIT: str = "repos:\n  - repo: https://github.com/astral-sh/ruff-pre-commit\n    rev: v0.17.2\n    hooks:\n      - id: ruff-check\n"
CHECKOUT: str = "      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1\n"
SETUP_UV: str = "        uses: astral-sh/setup-uv@07a047e608db84b3d8c06cd9a7c7dcc9c355c18e # v10.3.2\n"


def test_dev_requirements_match_when_the_repository_declares_each_baseline_entry() -> None:
    """Entries only the repository declares, and differences in comments or order, are not mismatches."""
    repo: str = '[dependency-groups]\ndev = [\n    "duckdb>=2.0.0,<3",  # repo only\n    "ruff>=0.17.2,<0.18",\n    "MyPy >= 2.4, < 3",\n]\n'
    assert dev_requirement_mismatches(repo, BASELINE) == []


@pytest.mark.parametrize(
    ("repo", "message"),
    [
        ('[dependency-groups]\ndev = ["mypy>=2.4,<3", "ruff>=0.17.3,<0.18"]\n', "ruff: baseline ruff<0.18,>=0.17.2, repository ruff<0.18,>=0.17.3"),
        ('[dependency-groups]\ndev = ["mypy>=2.4,<3", "ruff>=0.17.2,<0.18; sys_platform != \'win32\'"]\n', 'ruff: baseline ruff<0.18,>=0.17.2, repository ruff<0.18,>=0.17.2; sys_platform != "win32"'),
        ('[dependency-groups]\ndev = ["mypy>=2.4,<3"]\n', "ruff: baseline ruff<0.18,>=0.17.2, repository None"),
    ],
    ids=["version", "marker", "missing"],
)
def test_dev_requirements_report_each_baseline_entry_the_repository_declares_differently(repo: str, message: str) -> None:
    assert dev_requirement_mismatches(repo, BASELINE) == [message]


def test_dev_requirements_fail_loudly_without_a_dev_group() -> None:
    """A renamed table must fail the check, never compare an empty list."""
    with pytest.raises(KeyError, match="dependency-groups"):
        dev_requirement_mismatches("[project]\n", BASELINE)


def test_ruff_hook_matches_the_baseline_minimum() -> None:
    assert ruff_hook_mismatches(BASELINE, PRE_COMMIT) == []


@pytest.mark.parametrize(
    ("pre_commit", "message"),
    [
        (PRE_COMMIT.replace("v0.17.2", "v0.17.3"), "ruff-pre-commit rev v0.17.3, baseline minimum ['0.17.2']"),
        ("repos:\n  - repo: local\n", "no ruff-pre-commit rev in the pre-commit config"),
    ],
    ids=["version", "missing"],
)
def test_ruff_hook_reports_a_rev_other_than_the_baseline_minimum(pre_commit: str, message: str) -> None:
    assert ruff_hook_mismatches(BASELINE, pre_commit) == [message]


def test_action_pins_match_when_each_action_has_one_pin() -> None:
    assert action_pin_mismatches({"ci.yml": CHECKOUT + SETUP_UV, "mutation.yml": CHECKOUT}) == []


@pytest.mark.parametrize(
    ("workflows", "message"),
    [
        (
            {"ci.yml": CHECKOUT, "mutation.yml": CHECKOUT.replace("v7.0.1", "v7.0.2")},
            "actions/checkout: 3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1 | 3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.2",
        ),
        ({"ci.yml": CHECKOUT, "mutation.yml": "      - uses: actions/checkout@v7\n"}, "mutation.yml: actions/checkout@v7 is not pinned to a SHA with a version comment"),
        ({"ci.yml": "jobs: {}\n"}, "no pinned actions in the workflows"),
    ],
    ids=["two-pins", "unpinned", "none"],
)
def test_action_pins_report_each_action_without_exactly_one_pin(workflows: dict[str, str], message: str) -> None:
    assert action_pin_mismatches(workflows) == [message]


@pytest.mark.no_mutation
def test_repository_declares_the_baseline_dev_requirements() -> None:
    """Projects set up from the baseline get the tool versions this repository runs its own checks with."""
    assert dev_requirement_mismatches((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"), (ASSETS / "pyproject-baseline.toml").read_text(encoding="utf-8")) == []


@pytest.mark.no_mutation
def test_pre_commit_runs_the_baseline_ruff() -> None:
    """The hook and ``uv run ruff`` must agree, or a commit and CI disagree on which rules fire."""
    assert ruff_hook_mismatches((ASSETS / "pyproject-baseline.toml").read_text(encoding="utf-8"), (ASSETS / "pre-commit-config.yaml").read_text(encoding="utf-8")) == []


@pytest.mark.no_mutation
def test_workflows_pin_each_action_once() -> None:
    """The repository's own workflows, plus the templates setup-standards.sh writes into other projects.

    Keyed by path: the repository's ``ci.yml`` and the template ``ci.yml`` share a name.
    """
    workflows: list[Path] = workflow_files(REPO_ROOT.parent / ".github" / "workflows", ASSETS)
    assert action_pin_mismatches({path.relative_to(REPO_ROOT.parent).as_posix(): path.read_text(encoding="utf-8") for path in workflows}) == []


def test_workflow_files_include_both_yaml_extensions(tmp_path: Path) -> None:
    """GitHub runs ``.yaml`` workflows too; one left out would escape the pin check."""
    name: str
    for name in ("a.yaml", "b.yml", "notes.md"):
        (tmp_path / name).write_text("", encoding="utf-8")
    assert workflow_files(tmp_path) == [tmp_path / "a.yaml", tmp_path / "b.yml"]
