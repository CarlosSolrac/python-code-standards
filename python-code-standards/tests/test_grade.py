"""Tests for the eval grader.

The grader is a measurement tool, so its failure mode is reporting a plausible
number rather than raising. Every fault it has had so far — a stale default path,
run paths resolved twice, JSON buried in installer output — produced a confident
wrong answer. These tests pin the parsing and detection logic that made those
faults possible.

Ruff and Pyright invocations are not exercised here; they shell out to ``uvx`` and
belong to the runbook's manual verification, not to a unit test.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evals.grade import GRADER_VERSION, Score, _payload, count_declarations, grade, main, third_party_imports


@pytest.mark.parametrize(
    ("output", "opener", "expected"),
    [
        ('{"errorCount": 3}', "{", {"errorCount": 3}),
        ('Installed 1 package\n{"errorCount": 3}', "{", {"errorCount": 3}),
        ('{"errorCount": 3}\nwarning: cache miss\n', "{", {"errorCount": 3}),
        ('Resolved {2} packages\n{"errorCount": 3}', "{", {"errorCount": 3}),
        ("[]", "[", []),
        ('Downloading ruff (9.8MiB)\n[{"code": "F401"}]', "[", [{"code": "F401"}]),
        ("no payload at all", "{", None),
        ("", "{", None),
    ],
    ids=[
        "bare-object",
        "chatter-before",
        "stderr-after",
        "brace-in-chatter",
        "empty-array",
        "chatter-before-array",
        "no-payload",
        "empty-output",
    ],
)
def test_payload_extraction(output: str, opener: str, expected: object) -> None:
    """The first complete JSON value is recovered regardless of surrounding text."""
    assert _payload(output, opener) == expected


def test_payload_ignores_trailing_second_object() -> None:
    """Only the first value is returned; trailing values do not break parsing."""
    assert _payload('{"a": 1}\n{"b": 2}', "{") == {"a": 1}


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("import duckdb", ["duckdb"]),
        ("import json\nimport sys", []),
        ("from pathlib import Path", []),
        ("import duckdb\nimport json\nimport pytest", ["duckdb", "pytest"]),
        ("from duckdb.typing import BIGINT", ["duckdb"]),
        ("from . import sibling", []),
        ("import duckdb.functional", ["duckdb"]),
    ],
    ids=["third-party", "stdlib-only", "stdlib-from", "mixed", "submodule-from", "relative", "dotted"],
)
def test_third_party_imports(tmp_path: Path, source: str, expected: list[str]) -> None:
    """Only non-stdlib, non-local, absolute imports are reported."""
    (tmp_path / "module.py").write_text(source, encoding="utf-8")
    assert third_party_imports(tmp_path) == expected


def test_third_party_imports_excludes_sibling_modules(tmp_path: Path) -> None:
    """A module in the run is local, not a package to install."""
    (tmp_path / "helpers.py").write_text("", encoding="utf-8")
    (tmp_path / "main.py").write_text("import helpers\nimport duckdb", encoding="utf-8")
    assert third_party_imports(tmp_path) == ["duckdb"]


def test_third_party_imports_skips_unparseable_files(tmp_path: Path) -> None:
    """A syntax error in one file does not hide imports in the others."""
    (tmp_path / "broken.py").write_text("def (:\n", encoding="utf-8")
    (tmp_path / "ok.py").write_text("import duckdb", encoding="utf-8")
    assert third_party_imports(tmp_path) == ["duckdb"]


def test_count_declarations_uses_absolute_paths(tmp_path: Path) -> None:
    """Counting must not depend on the caller's working directory.

    The grader runs the checker from a different directory than the one it was
    given; a relative run path used to resolve twice and silently match nothing.
    """
    run: Path = tmp_path / "runs" / "sample"
    run.mkdir(parents=True)
    (run / "m.py").write_text("x = 1\nfor y in []:\n    pass\n", encoding="utf-8")
    checker: Path = Path(__file__).parent.parent / "skill" / "tools" / "check_declarations.py"
    assert count_declarations(run.resolve(), checker.resolve()) == 2


def test_grade_records_version_and_counts(tmp_path: Path) -> None:
    """A graded run carries the grader version and the declaration count."""
    run: Path = tmp_path / "sample"
    run.mkdir()
    (run / "m.py").write_text("total = 0\n", encoding="utf-8")
    checker: Path = Path(__file__).parent.parent / "skill" / "tools" / "check_declarations.py"
    config: Path = Path(__file__).parent.parent / "pyproject.toml"

    score: Score = grade(run.resolve(), checker.resolve(), config.resolve())
    assert score.grader_version == GRADER_VERSION
    assert score.declaration_violations == 1
    assert score.files == 1


def test_grade_notes_missing_python_files(tmp_path: Path) -> None:
    """An empty run directory is called out rather than scored as clean."""
    run: Path = tmp_path / "empty"
    run.mkdir()
    checker: Path = Path(__file__).parent.parent / "skill" / "tools" / "check_declarations.py"
    config: Path = Path(__file__).parent.parent / "pyproject.toml"

    score: Score = grade(run.resolve(), checker.resolve(), config.resolve())
    assert any("no Python files" in note for note in score.notes)


def test_grade_flags_pip_usage(tmp_path: Path) -> None:
    """The standards require uv, so a pip invocation in the output is noted."""
    run: Path = tmp_path / "sample"
    run.mkdir()
    (run / "setup.py").write_text('# run: pip install duckdb\nname: str = "x"\n', encoding="utf-8")
    checker: Path = Path(__file__).parent.parent / "skill" / "tools" / "check_declarations.py"
    config: Path = Path(__file__).parent.parent / "pyproject.toml"

    score: Score = grade(run.resolve(), checker.resolve(), config.resolve())
    assert any("pip" in note for note in score.notes)


def test_score_serializes_to_json(tmp_path: Path) -> None:
    """Scores must round-trip through the --json output path."""
    run: Path = tmp_path / "sample"
    run.mkdir()
    (run / "m.py").write_text("value: int = 1\n", encoding="utf-8")
    checker: Path = Path(__file__).parent.parent / "skill" / "tools" / "check_declarations.py"
    config: Path = Path(__file__).parent.parent / "pyproject.toml"

    score: Score = grade(run.resolve(), checker.resolve(), config.resolve())
    restored: dict[str, object] = json.loads(json.dumps(score.__dict__))
    assert restored["grader_version"] == GRADER_VERSION


def test_main_prints_table_and_returns_zero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The CLI reports rather than gates, so it exits zero even with violations."""
    run: Path = tmp_path / "sample"
    run.mkdir()
    (run / "m.py").write_text("x = 1\n", encoding="utf-8")
    root: Path = Path(__file__).parent.parent

    status: int = main([str(run), "--checker", str(root / "skill" / "tools" / "check_declarations.py"), "--config", str(root / "pyproject.toml")])
    captured: str = capsys.readouterr().out
    assert status == 0
    assert GRADER_VERSION in captured
    assert "decl" in captured


def test_main_writes_json_with_version(tmp_path: Path) -> None:
    """The --json path records the grader version for cross-run comparison."""
    run: Path = tmp_path / "sample"
    run.mkdir()
    (run / "m.py").write_text("value: int = 1\n", encoding="utf-8")
    root: Path = Path(__file__).parent.parent
    out: Path = tmp_path / "scores.json"

    main([str(run), "--checker", str(root / "skill" / "tools" / "check_declarations.py"), "--config", str(root / "pyproject.toml"), "--json", str(out)])
    written: list[dict[str, object]] = json.loads(out.read_text(encoding="utf-8"))
    assert written[0]["grader_version"] == GRADER_VERSION


def test_count_declarations_returns_negative_on_checker_failure(tmp_path: Path) -> None:
    """A checker that cannot run is reported as -1, never as zero violations."""
    run: Path = tmp_path / "sample"
    run.mkdir()
    (run / "m.py").write_text("x = 1\n", encoding="utf-8")
    assert count_declarations(run.resolve(), tmp_path / "does-not-exist.py") == -1
