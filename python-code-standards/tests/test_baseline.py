"""Behaviour of a project configured from ``skill/assets/pyproject-baseline.toml``."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

REPO_ROOT: Path = Path(__file__).resolve().parent.parent
BASELINE: Path = REPO_ROOT / "skill" / "assets" / "pyproject-baseline.toml"


def test_tests_import_project_code(pytester: pytest.Pytester) -> None:
    """A test in ``tests/`` imports a top-level package with no install step.

    The baseline has no build system, so the project is never installed, and
    ``tests/`` has no ``__init__.py`` (INP001 is waived there). The run is in
    process because ``runpytest_subprocess`` puts the project root on
    ``PYTHONPATH``, which would hide a missing ``pythonpath`` setting.
    """
    shutil.copy(BASELINE, pytester.path / "pyproject.toml")
    (pytester.path / "probe").mkdir()
    (pytester.path / "probe" / "__init__.py").write_text("VALUE: int = 1\n", encoding="utf-8")
    (pytester.path / "tests").mkdir()
    (pytester.path / "tests" / "test_probe.py").write_text("from probe import VALUE\n\n\ndef test_value() -> None:\n    assert VALUE == 1\n", encoding="utf-8")

    result: pytest.RunResult = pytester.runpytest_inprocess("-p", "no:cacheprovider")
    result.assert_outcomes(passed=1)
