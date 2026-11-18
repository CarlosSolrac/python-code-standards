"""Tests for copying each vendored file into its heredoc in the setup script."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

import pytest

from skill.tools.vendor_templates import main, vendor

SCRIPT: str = """\
#!/usr/bin/env bash
write_file .pre-commit-config.yaml <<'YAML'
rev: v1
YAML

write_file .gitignore <<'IGNORE'
.venv/
IGNORE
"""


def test_vendor_replaces_only_the_named_heredocs() -> None:
    assert vendor(SCRIPT, {"YAML": "rev: v2\nhooks: []\n"}) == SCRIPT.replace("rev: v1\n", "rev: v2\nhooks: []\n")


def test_vendor_fills_an_empty_heredoc() -> None:
    assert vendor("cat <<'YAML'\nYAML\necho done\n", {"YAML": "a\n"}) == "cat <<'YAML'\na\nYAML\necho done\n"


def test_vendor_follows_bash_heredoc_rules() -> None:
    """Only a line that is exactly the delimiter closes the body."""
    script: str = "write_file a <<'YAML'\nold\nYAML  \nYAMLX\nYAML\necho done\n"
    assert vendor(script, {"YAML": "new\n"}) == "write_file a <<'YAML'\nnew\nYAML\necho done\n"


def test_vendor_fails_loudly_when_a_heredoc_is_missing() -> None:
    """A renamed heredoc must fail the update, never leave the old copy in place."""
    with pytest.raises(ValueError, match=r"no heredoc <<'CI' in the setup script"):
        vendor(SCRIPT, {"CI": "on: push\n"})


def test_main_copies_the_sources_into_the_script(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    script: Path = tmp_path / "setup.sh"
    script.write_text(SCRIPT, encoding="utf-8", newline="")
    source: Path = tmp_path / "pre-commit-config.yaml"
    source.write_text("rev: v2\n", encoding="utf-8", newline="")

    assert main([], script=script, sources={"YAML": source}) == 0
    assert script.read_text(encoding="utf-8") == SCRIPT.replace("rev: v1\n", "rev: v2\n")
    assert capsys.readouterr().out == f"updated {script}\n"
    assert main([], script=script, sources={"YAML": source}) == 0
    assert capsys.readouterr().out == f"{script} is up to date\n"


def test_runs_as_a_module(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """Run with ``python -m``, the module exits with ``main``'s status."""
    monkeypatch.setattr(sys, "argv", ["vendor_templates", "--help"])
    # runpy warns when the module it runs as __main__ is already imported.
    monkeypatch.delitem(sys.modules, "skill.tools.vendor_templates")
    exit_info: pytest.ExceptionInfo[SystemExit]
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module("skill.tools.vendor_templates", run_name="__main__")
    assert exit_info.value.code == 0
    assert "uv run python -m skill.tools.vendor_templates" in capsys.readouterr().out
