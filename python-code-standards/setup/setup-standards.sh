#!/usr/bin/env bash
#
# setup-standards.sh -- configure a repository to follow the python-code-standards.
#
# Run it from inside the target repository; it operates on the repo your current
# directory is in, not on wherever this file lives:
#
#   cd ~/src/my-repo
#   ~/src/python-code-standards/python-code-standards/setup/setup-standards.sh
#
#   -y, --yes    never ask (required when stdin is not a tty); replace only what
#                --update or --force allows; record the default models only
#                when none are recorded yet
#   --update     with --yes, replace files an earlier version of this script
#                wrote and nobody edited since, and add the dev tools
#                pyproject.toml lacks
#   --force      like --update, and also replace edited files, saving each as
#                <file>.orig first; without --yes it asks before doing so
#   -h, --help   print this header
#
# Self-contained: every template below is embedded, so the script also works
# copied on its own to a host with no clone of the standards repo. The embedded
# tools are kept byte-identical to skill/tools/ by tests/test_setup_script.py.
#
# It installs these files, then bootstraps the environment:
#   pyproject.toml              ruff / pyright / mypy / pytest / coverage config
#   .pre-commit-config.yaml     the lint + type verification loop
#   .gitattributes              eol=lf as a property of the repo
#   .gitignore                  Python caches and build output
#   .github/workflows/ci.yml    CI: pre-commit --all-files + pytest --cov + diff-cover
#   tools/check_declarations.py the "annotate before first binding" checker
#   tools/__init__.py           makes tools importable as a package
#   tools/check_suppressions.py fails on a suppression added without approval
#   tools/check_coverage_records.py  CI: fails on a changed module no test imports
#   tools/changes.py            git helpers shared by the two checks above
#   tools/review_brief.py       one-screen brief of where to look; the Stop hook shows it
#   suppressions.toml           the approved suppressions (path, code, reason)
#   tools/mutation.sh           mutation testing (mutmut); on Windows run it in WSL
#   .github/workflows/mutation.yml  nightly, report-only mutation run
#   tools/hooks/                Claude Code hooks: ask before a gate changes; block
#                               "done" until the gates pass on changed files
#   .claude/settings.json       registers those hooks for this project
#   tests/.gitkeep              pytest testpaths root
#
# A missing file is created. An existing one is compared with the template:
#   current   identical; nothing to do
#   outdated  written by an earlier version of this script and never edited,
#             recognized by the digests embedded below. Nothing is lost by
#             replacing it: an interactive run lists these and asks once;
#             --yes replaces them only with --update.
#   edited    anything else. Kept, unless --force replaces it after saving
#             <file>.orig.
# pyproject.toml is always edited by the project, so it is compared one
# [tool.*] table at a time, and a replaced table is swapped in place, leaving
# every other line as it was; the file is saved as pyproject.toml.orig first.
# Dev tools pyproject.toml lacks are listed, then added with "uv add --dev"
# after asking, or unasked with --yes --update; a tool it already names keeps
# its version. Without pre-commit, the git hook is reported as not installed.
#
# Before installing, it asks three questions: the coordinator model (the main
# session's default; it runs the tests), the coding model (agents that write
# code), and the adversarial code-review provider (codex or claude), then its
# model. Model names are free text. The answers go in a block of
# ~/.claude/CLAUDE.md between <!-- python-code-standards:models --> and
# <!-- /python-code-standards:models -->, and the coordinator in "model" of
# ~/.claude/settings.json. Every write is shown and confirmed first. A re-run
# offers the stored answers as defaults; -y writes the defaults (sonnet,
# opus, codex gpt-5.4) only when no block exists, and never replaces
# an existing settings.json "model". The models step fails when CLAUDE.md holds
# markers that are not exactly one closed block (nothing is written), or when -y
# skips a file that is a link resolving outside the home directory (without -y,
# such a write is asked); setup then carries on and fails at the end.
#
# The same step installs the embedded skills, python-code-standards and
# review-standards, in the chosen hosts' homes (~/.claude/skills,
# ~/.copilot/skills, ~/.agents/skills for a Codex reviewer), each directory
# marked with .managed-by; a directory setup did not mark, or a link, is
# reported and left alone. A Codex reviewer also gets a review scope block in
# ~/.codex/AGENTS.md. This script copies itself to
# ~/.local/share/python-code-standards/setup-standards.sh, where an installed
# skill finds it. skill/references/setup.md has the details.

set -euo pipefail

# --------------------------------------------------------------------------- #
# Arguments
# --------------------------------------------------------------------------- #

ASSUME_YES=0
INSTALL_FLAGS=()
MODEL_FLAGS=()
arg=""
for arg in "$@"; do
    case "$arg" in
        -y | --yes)
            ASSUME_YES=1
            INSTALL_FLAGS+=(--yes)
            MODEL_FLAGS+=(--yes)
            ;;
        --update | --force) INSTALL_FLAGS+=("$arg") ;;
        -h | --help)
            # The header: every comment line after the shebang, up to the code.
            awk 'NR == 1 { next } /^#/ { sub(/^# ?/, ""); print; next } { exit }' "$0"
            exit 0
            ;;
        *)
            printf 'unknown argument: %s (try --help)\n' "$arg" >&2
            exit 2
            ;;
    esac
done

# --------------------------------------------------------------------------- #
# Preconditions
# --------------------------------------------------------------------------- #

die() {
    printf 'error: %s\n' "$1" >&2
    exit 1
}

command -v git >/dev/null 2>&1 || die "git not found on PATH"
command -v uv >/dev/null 2>&1 || die "uv not found on PATH -- https://docs.astral.sh/uv/getting-started/installation/"

# This script's absolute path, for the copy setup keeps of it; taken before the cd below.
INSTALLER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || die "not inside a git repository (run 'git init' first)"
cd "$REPO_ROOT"

# Refuse to scaffold the standards repo itself -- the usual "forgot to cd" slip.
# The skill may sit at the repo root or one directory down (this repo nests it
# under python-code-standards/).
if [ -f "$REPO_ROOT/skill/SKILL.md" ] || compgen -G "$REPO_ROOT/*/skill/SKILL.md" >/dev/null 2>&1; then
    die "this looks like the python-code-standards repo; cd into your target repo first"
fi

PROJECT_NAME="$(basename "$REPO_ROOT")"

if [ "$ASSUME_YES" -ne 1 ]; then
    printf 'Configure %s to follow the python-code-standards? [y/N] ' "$REPO_ROOT"
    reply=""
    read -r reply || reply=""
    case "$reply" in
        [yY] | [yY][eE][sS]) ;;
        *) die "aborted (pass -y to skip this prompt)" ;;
    esac
fi

printf '\nConfiguring %s at %s\n\n' "$PROJECT_NAME" "$REPO_ROOT"

# --------------------------------------------------------------------------- #
# Templates are staged first; setup_files.py (below) decides what reaches the
# repository, comparing each with what is already there.
# --------------------------------------------------------------------------- #

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
FILES="$WORK/files"
mkdir -p "$FILES"

write_file() {
    # Stage stdin as the template for repository path $1.
    mkdir -p "$(dirname "$FILES/$1")"
    cat >"$FILES/$1"
}

# The skills setup_models.py installs in each host's home, one folder per skill.
MODULES="$WORK/modules"

module_file() {
    # Stage stdin as file $1 of an installed skill, a path under $MODULES.
    mkdir -p "$(dirname "$MODULES/$1")"
    cat >"$MODULES/$1"
}

# --------------------------------------------------------------------------- #
# pyproject.toml -- baseline verbatim, with only [project] name substituted.
# The baseline itself is staged for the installed skill's assets/.
# A repo directory name with '|' in it would break the sed; rename by hand then.
# --------------------------------------------------------------------------- #

module_file python-code-standards/assets/pyproject-baseline.toml <<'TOML'
##
## Baseline tooling configuration for a new Python project.
## Use the repository's existing configuration when one is already present.
##

[project]
name = "example-project"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = []

[dependency-groups]
dev = [
    "complexipy>=9.0.0,<10",           # cognitive complexity cap, see [tool.complexipy]
    "deptry>=0.25,<0.26",         # unused, missing, and transitive dependencies
    "diff-cover>=11.0.2,<12",        # CI: 100% coverage of changed lines
    "mutmut>=3.8.1,<4; sys_platform != 'win32'",  # needs os.fork; on Windows run it through WSL
    "mypy>=2.4.1,<3",
    "pip-audit>=2.10.1,<3",         # CI: dependencies with known vulnerabilities
    "pre-commit>=4.7.0,<5",
    "pyright>=1.1.414,<2",       # PyPI wrapper; downloads a Node runtime on first run
    "pytest>=9.2.0,<10",         # 9.0.3 fixes PYSEC-2026-1845
    "pytest-cov>=7.1.0,<8",
    "ruff>=0.17.5,<0.18",       # pinned: minor releases change which rules fire
]

[tool.ruff]
target-version = "py313"
# Without this, notebooks are silently exempt from every rule below.
extend-include = ["*.ipynb"]
line-length = 220
indent-width = 4

[tool.ruff.lint]
select = [
    "E4", "E7", "E9", "F",   # pycodestyle subset + pyflakes
    "I",                      # import sorting
    "B",                      # bugbear
    "UP",                     # pyupgrade
    "SIM",                    # simplify
    "RUF",                    # ruff-specific
    "D",                      # pydocstyle
    "ANN",                    # missing annotations
    "PTH",                    # pathlib over os.path
    "S",                      # bandit security checks
    "RET",                    # return-statement hygiene
    "C4",                     # comprehension quality
    "LOG", "G",               # logging correctness and format style
    "TID",                    # tidy imports
    "N",                      # pep8-naming
    "A",                      # builtin shadowing
    "ARG",                    # unused arguments
    "DTZ",                    # timezone-aware datetimes
    "ERA",                    # commented-out code
    "T20",                    # stray print
    "SLF",                    # private member access
    "PGH",                    # blanket noqa / bare type-ignore
    "PT",                     # pytest style
    "ASYNC",                  # async correctness
    "INP",                    # implicit namespace packages
    "C90",                    # cyclomatic complexity, capped in [tool.ruff.lint.mccabe]
    "PLR",                    # refactor: too many branches, arguments, returns; magic values
    "BLE",                    # blind except
    "TRY",                    # exception-handling anti-patterns
    "FBT",                    # boolean positional-argument traps
    "PERF",                   # performance anti-patterns
    "PIE",                    # unnecessary code
    "FURB",                   # modernization
    "RSE",                    # raise hygiene
    "EM",                     # exception messages bound before the raise
]
ignore = []
fixable = ["ALL"]
unfixable = []

[tool.ruff.lint.per-file-ignores]
# pytest's assert-based style and test-only fixtures trip the bandit rules.
# pytest's assert-based style trips bandit; test names carry the meaning that
# a mandatory docstring would only restate, so docstrings in tests are optional.
# Literal expected values are the specification in a test, so magic numbers
# (PLR2004) are allowed there.
"tests/**/*.py" = ["S101", "S105", "S106", "D100", "D103", "INP001", "PLR2004"]
# A file named test_*.py is a test file wherever it sits. Without these two
# patterns the ignores above never match a test written beside its module.
"test_*.py" = ["S101", "S105", "S106", "D100", "D103", "INP001", "PLR2004"]
"**/test_*.py" = ["S101", "S105", "S106", "D100", "D103", "INP001", "PLR2004"]
"conftest.py" = ["S101", "D100", "INP001"]
# AST and metaprogramming code cannot satisfy strict unknown-type reporting.
# A CLI tool prints by design; that is the intentional-output carve-out.
"tools/**/*.py" = ["INP001", "T201"]

[tool.ruff.lint.pydocstyle]
# This already disables the conflicting D rules; do not add redundant D2xx ignores.
convention = "google"

[tool.ruff.lint.flake8-tidy-imports]
ban-relative-imports = "parents"

[tool.ruff.lint.mccabe]
max-complexity = 10

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
skip-magic-trailing-comma = false
line-ending = "lf"
docstring-code-format = true
docstring-code-line-length = "dynamic"

[tool.pyright]
typeCheckingMode = "strict"
pythonVersion = "3.13"
reportMissingTypeStubs = true
reportUnknownMemberType = true
# A suppression that no longer suppresses anything is noise that hides the next real one.
reportUnnecessaryTypeIgnoreComment = "error"
stubPath = "stubs"

[[tool.pyright.executionEnvironments]]
# AST walking and other metaprogramming cannot satisfy strict unknown-type
# reporting without scattering ignores. Relax deliberately, in one place.
root = "tools"
reportUnknownMemberType = false
reportUnknownVariableType = false
reportUnknownArgumentType = false

[tool.mypy]
python_version = "3.13"
strict = true
warn_unreachable = true
disallow_any_explicit = false

[tool.pytest.ini_options]
addopts = "--strict-config --strict-markers"
# Mutation runs skip these: they run code in a child process, where mutants
# cannot be switched on, or compare source bytes that mutmut rewrites.
markers = ["no_mutation: needs the unmutated source or a child process; skipped by mutmut"]
# An xfail that starts passing, or a warning nobody reads, is a test that stopped testing.
xfail_strict = true
filterwarnings = ["error"]
testpaths = ["tests"]
# No build system, so the project is never installed; tests import it from the root.
pythonpath = ["."]

[tool.mutmut]
# Mutation testing (tools/mutation.sh): a surviving mutant is a code change no
# test noticed. Required before the first run: list the code to mutate, e.g.
#   source_paths = ["mypackage"]
# mutmut's own guess uses the checkout folder's name, which breaks in clones and CI.
pytest_add_cli_args_test_selection = ["tests/"]
pytest_add_cli_args = ["-m", "not no_mutation"]

[tool.complexipy]
# Cognitive complexity per function; Ruff's C90 caps cyclomatic complexity at 10.
max-complexity-allowed = 15

[tool.coverage.run]
branch = true

[tool.coverage.report]
# Whole-project floor. A project adopting this with untested legacy code starts
# at its current coverage and only raises it; CI's diff-cover step holds changed
# lines at 100% either way.
fail_under = 100
show_missing = true
TOML
sed "s|^name = \"example-project\"\$|name = \"${PROJECT_NAME}\"|" "$MODULES/python-code-standards/assets/pyproject-baseline.toml" >"$FILES/pyproject.toml"

# --------------------------------------------------------------------------- #
# .pre-commit-config.yaml
# --------------------------------------------------------------------------- #

write_file .pre-commit-config.yaml <<'YAML'
# Baseline hooks. `uv run pre-commit run --files <changed files>` is the whole
# verification loop except execution and coverage, which stay manual because
# they need the narrowest practical entry point chosen per change.
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.17.5
    hooks:
      - id: ruff-check
        args: [--fix]
      - id: ruff-format
  - repo: local
    hooks:
      - id: check-declarations
        name: every variable annotated before first binding
        entry: uv run python tools/check_declarations.py
        language: system
        types: [python]
      - id: pyright
        name: pyright (strict)
        entry: uv run pyright
        language: system
        types: [python]
        pass_filenames: true
      - id: mypy
        name: mypy (strict)
        entry: uv run mypy
        language: system
        types: [python]
        pass_filenames: true
        # Parallel batches share .mypy_cache and crash mypy on a cold cache.
        require_serial: true
      - id: check-suppressions
        name: no unapproved suppressions on added lines
        entry: uv run python -m tools.check_suppressions
        language: system
        # pre-commit tags notebooks "jupyter", not "python"; the check reads both.
        types_or: [python, jupyter]
      - id: complexipy
        name: cognitive complexity (complexipy)
        entry: uv run complexipy
        language: system
        types: [python]
      - id: deptry
        name: imports match declared dependencies (deptry)
        entry: uv run deptry .
        language: system
        # Whole-project check: an import or a pyproject.toml edit can break it.
        files: (\.py|pyproject\.toml)$
        pass_filenames: false
  # Scans staged content only, so it guards commits; pre-commit installs Go itself.
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.30.1
    hooks:
      - id: gitleaks
YAML

# --------------------------------------------------------------------------- #
# .gitattributes
# --------------------------------------------------------------------------- #

write_file .gitattributes <<'ATTR'
# Line endings are a property of the repository, not of each machine's git config.
# Without this, a clone on Windows depends on core.autocrlf being set locally.
* text=auto eol=lf
ATTR

# --------------------------------------------------------------------------- #
# .gitignore -- only when the repo has none
# --------------------------------------------------------------------------- #

write_file .gitignore <<'IGNORE'
.venv/
__pycache__/
*.py[cod]
.pytest_cache/
.ruff_cache/
.mypy_cache/
.pyright/
.coverage
coverage.xml
htmlcov/
dist/
build/
*.egg-info/
mutants/
IGNORE

# --------------------------------------------------------------------------- #
# .github/workflows/ci.yml
# --------------------------------------------------------------------------- #

write_file .github/workflows/ci.yml <<'CI'
name: verify

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

# A newer push to the same pull request supersedes the run in progress; runs on
# main always finish, so every merged commit keeps its result.
concurrency:
  group: verify-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}

jobs:
  verify:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          fetch-depth: 0 # diff-cover compares against the base branch
          persist-credentials: false

      - name: Install uv
        uses: astral-sh/setup-uv@68559e99cc807c1eb7e9238fd43a15bba460eec2 # v10.3.3
        with:
          enable-cache: true

      # Applications commit uv.lock and must install from it exactly.
      # Libraries do not commit one, so they resolve at install time.
      # This is a property of the repository, declared here once — never
      # detected at runtime, because a workflow that drops --locked when the
      # lockfile is missing fails open the moment someone deletes it.
      - name: Sync the environment (application; commits uv.lock)
        run: uv sync --locked --all-groups
      # For a library, replace the step above with:
      #   run: uv sync --all-groups

      # Ruff, formatting, the declaration checker, and both type checkers.
      # Runs over every file so a Ruff upgrade that changes which rules fire
      # is caught here rather than in someone's next diff.
      - name: Lint, format, declarations, types
        run: uv run pre-commit run --all-files --show-diff-on-failure

      # fail_under in pyproject.toml is the floor for the whole project; the
      # standard is 100% of the lines a change touches, which diff-cover
      # enforces, so untested legacy code does not block a covered change.
      - name: Tests and coverage
        run: uv run pytest --cov --cov-report=term-missing --cov-report=xml --cov-branch

      # A module no test imports never reaches coverage.xml, and diff-cover
      # silently skips files without a record, so it would pass untested code.
      - name: Every changed module has a coverage record
        run: uv run python -m tools.check_coverage_records --base origin/${{ github.base_ref || 'main' }}

      - name: Coverage of changed lines
        run: uv run diff-cover coverage.xml --compare-branch=origin/${{ github.base_ref || 'main' }} --fail-under=100

      # In CI the tree is HEAD, so pre-commit's suppression check sees no added
      # lines; this compares the branch against its merge base instead.
      - name: No unapproved suppressions on this branch
        run: uv run python -m tools.check_suppressions --base origin/${{ github.base_ref || 'main' }}

      - name: Dependencies with known vulnerabilities
        run: uv run pip-audit
CI

# --------------------------------------------------------------------------- #
# tools/check_declarations.py -- kept byte-identical to skill/tools/ by
# tests/test_setup_script.py in the standards repo.
# --------------------------------------------------------------------------- #

write_file tools/check_declarations.py <<'PYEOF'
"""Enforce the house rule that every variable is annotated before its first binding.

No existing linter checks this: Ruff's ANN rules cover signatures, not local
bindings. This walks each scope in source order and reports any name that is
bound before it carries an annotation.

Instance attributes are covered too: ``self.total = 0`` requires ``total: int`` in
the class body. Dataclass and Pydantic model fields satisfy this by construction,
since their fields *are* class-body annotations.

Exempt, because the language provides no way to annotate them: comprehension and
generator targets, ``except ... as`` names, walrus bindings, imports, function and
class definitions, function parameters (annotated in the signature), and enum
members (the typing spec forbids annotating them). An enum is a class whose base
is an enum class defined earlier in the same file, or resolves through the file's
imports to a standard-library enum base (``enum.Enum``, ``enum.StrEnum``, ...) or
to a base listed in ``pyproject.toml``. List enum bases defined in other modules,
your own or a library's, by their fully qualified import names:

    [tool.check-declarations]
    enum-bases = ["myproject.base.BaseStatus", "django.db.models.TextChoices"]

Relative imports resolve against the file's package, found by walking up through
directories that hold an ``__init__.py``.

Usage:
    uv run python -m tools.check_declarations src tests
Exit status is 1 when any violation is found.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
import tomllib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

_STDLIB_ENUM_BASES: frozenset[str] = frozenset({"enum.Enum", "enum.IntEnum", "enum.StrEnum", "enum.Flag", "enum.IntFlag", "enum.ReprEnum"})
"""Enum base classes the ``enum`` module exports; members of their subclasses can't be annotated."""

PYPROJECT: Path = Path("pyproject.toml")


@dataclass(frozen=True)
class Violation:
    """A name bound in a scope before it was annotated."""

    path: Path
    line: int
    column: int
    name: str
    hint: str = ""

    def render(self) -> str:
        """Return a single-line, editor-navigable description."""
        message: str = f"{self.path}:{self.line}:{self.column}: {self.name} bound before annotation"
        return f"{message} ({self.hint})" if self.hint else message


class AttributeChecker(ast.NodeVisitor):
    """Flag ``self.<name>`` assignments whose name is not declared in the class body."""

    def __init__(self, path: Path, receiver: str, declared: set[str]) -> None:
        """Initialize the checker.

        Args:
            path: File being checked, used for reporting.
            receiver: Name of the method's first parameter, usually ``self``.
            declared: Attribute names annotated in the class body or an in-file base.
        """
        self.path: Path = path
        self.receiver: str = receiver
        self.declared: set[str] = declared
        self.violations: list[Violation] = []

    def _check(self, node: ast.expr) -> None:
        """Report an attribute target that carries no class-body declaration."""
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == self.receiver:
            if node.attr not in self.declared:
                self.violations.append(Violation(self.path, node.lineno, node.col_offset, f"{self.receiver}.{node.attr}"))
            self.declared.add(node.attr)
            return
        if isinstance(node, (ast.Tuple, ast.List)):
            element: ast.expr
            for element in node.elts:
                self._check(element)

    def visit_Assign(self, node: ast.Assign) -> None:
        """Check every assignment target."""
        target: ast.expr
        for target in node.targets:
            self._check(target)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        """An inline annotation declares the attribute at its first binding."""
        if isinstance(node.target, ast.Attribute) and isinstance(node.target.value, ast.Name) and node.target.value.id == self.receiver:
            self.declared.add(node.target.attr)
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        """A loop may bind an attribute directly."""
        self._check(node.target)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Do not descend into nested functions; the receiver may differ."""

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Do not descend into nested async functions."""


class ScopeChecker(ast.NodeVisitor):
    """Check one lexical scope, then recurse into nested scopes."""

    def __init__(self, path: Path, declared: set[str], enum_bases: frozenset[str], package: str) -> None:
        """Initialize the checker.

        Args:
            path: File being checked, used for reporting.
            declared: Names already annotated or otherwise exempt in this scope.
            enum_bases: Fully qualified names of the enum base classes to recognize.
            package: The module's package, against which relative imports resolve.
        """
        self.path: Path = path
        self.declared: set[str] = set(declared)
        self.violations: list[Violation] = []
        self.class_attributes: dict[str, set[str]] = {}
        self.enum_bases: frozenset[str] = enum_bases
        self.package: str = package
        # Fully qualified names of imported bindings, and names bound to in-file enum classes.
        self.imports: dict[str, str] = {}
        self.enum_classes: set[str] = set()
        self.in_enum_body: bool = False
        self.member_hint: str = ""
        # A class body is not an enclosing scope for its methods, so a class-body
        # checker hands its functions the names visible where the class is defined.
        self.visible_to_functions: set[str] = self.declared

    def _bind(self, node: ast.expr) -> None:
        """Record a binding target, reporting it when it lacks a prior annotation."""
        if isinstance(node, ast.Name):
            if node.id not in self.declared and not node.id.startswith("__"):
                self.violations.append(Violation(self.path, node.lineno, node.col_offset, node.id, self.member_hint))
            self.declared.add(node.id)
            return
        if isinstance(node, (ast.Tuple, ast.List)):
            element: ast.expr
            for element in node.elts:
                self._bind(element)
            return
        if isinstance(node, ast.Starred):
            self._bind(node.value)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        """Treat an annotation as declaring the name, with or without a value."""
        if isinstance(node.target, ast.Name):
            self.declared.add(node.target.id)
        if node.value is not None:
            self.visit(node.value)

    def visit_Assign(self, node: ast.Assign) -> None:
        """Check every assignment target; enum members are exempt, since the typing spec forbids annotating them."""
        self.visit(node.value)
        target: ast.expr
        for target in node.targets:
            if not (self.in_enum_body and _is_member_target(target)):
                self._bind(target)

    def visit_For(self, node: ast.For | ast.AsyncFor) -> None:
        """Check the loop target, then the body."""
        self.visit(node.iter)
        self._bind(node.target)
        self.visit_body(node.body)
        self.visit_body(node.orelse)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:  # passthrough: allow -- NodeVisitor dispatches by name
        """Async loops behave identically."""
        self.visit_For(node)

    def visit_With(self, node: ast.With | ast.AsyncWith) -> None:
        """Check each ``as`` target, then the body."""
        item: ast.withitem
        for item in node.items:
            self.visit(item.context_expr)
            if item.optional_vars is not None:
                self._bind(item.optional_vars)
        self.visit_body(node.body)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:  # passthrough: allow -- NodeVisitor dispatches by name
        """Async context managers behave identically."""
        self.visit_With(node)

    def _bind_pattern(self, node: ast.pattern) -> None:
        """Record every name a structural pattern binds.

        ``MatchAs``, ``MatchStar``, and ``MatchMapping`` rest-targets are ordinary
        bindings and can be pre-declared, so the rule applies to them. Sub-patterns
        bind before the pattern's own name, matching their order in source.
        """
        sub: ast.pattern
        for sub in _sub_patterns(node):
            self._bind_pattern(sub)
        target: ast.Name | None = _pattern_target(node)
        if target is not None:
            self._bind(target)

    def visit_Match(self, node: ast.Match) -> None:
        """Check every case pattern, then each case body."""
        self.visit(node.subject)
        case: ast.match_case
        for case in node.cases:
            self._bind_pattern(case.pattern)
            if case.guard is not None:
                self.visit(case.guard)
            self.visit_body(case.body)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        """Exempt the handler name; it is unbound at the end of the block."""
        if node.name is not None:
            self.declared.add(node.name)
        self.visit_body(node.body)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        """Exempt walrus bindings, which cannot carry an annotation."""
        self.declared.add(node.target.id)
        self.visit(node.value)

    def _visit_comprehension(self, generators: list[ast.comprehension]) -> None:
        """Check each iterable; the targets are exempt and declare nothing here.

        A comprehension's targets occupy its own scope, so they are never bindings
        of the enclosing scope, and a later binding of the same name still needs
        its own annotation.
        """
        generator: ast.comprehension
        for generator in generators:
            self.visit(generator.iter)

    def visit_ListComp(self, node: ast.ListComp) -> None:
        """Handle list comprehensions."""
        self._visit_comprehension(node.generators)

    def visit_SetComp(self, node: ast.SetComp) -> None:
        """Handle set comprehensions."""
        self._visit_comprehension(node.generators)

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        """Handle generator expressions."""
        self._visit_comprehension(node.generators)

    def visit_DictComp(self, node: ast.DictComp) -> None:
        """Handle dict comprehensions."""
        self._visit_comprehension(node.generators)

    def visit_Import(self, node: ast.Import) -> None:
        """Imports bind names that cannot be annotated; each is recorded with the module it names."""
        alias: ast.alias
        for alias in node.names:
            bound: str = (alias.asname or alias.name).split(".")[0]
            self.declared.add(bound)
            self.enum_classes.discard(bound)
            self.imports[bound] = alias.name if alias.asname else bound

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Same treatment as plain imports; a relative import resolves against the file's package."""
        module: str | None = self._absolute_module(node.module, node.level)
        alias: ast.alias
        for alias in node.names:
            bound: str = alias.asname or alias.name
            self.declared.add(bound)
            self.enum_classes.discard(bound)
            if module is None:
                self.imports.pop(bound, None)
            else:
                self.imports[bound] = f"{module}.{alias.name}"

    def _absolute_module(self, module: str | None, level: int) -> str | None:
        """Return the absolute name of an imported module, or None when a relative import leaves the package."""
        if level == 0:
            return module
        parts: list[str] = self.package.split(".") if self.package else []
        if level - 1 >= len(parts):
            return None
        return ".".join([*parts[: len(parts) - level + 1], *([module] if module else [])])

    def visit_Global(self, node: ast.Global) -> None:
        """Names declared global are managed in the module scope."""
        self.declared.update(node.names)

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        """Names declared nonlocal are managed in an enclosing scope."""
        self.declared.update(node.names)

    def _enter_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda) -> None:
        """Recurse into a function body with its parameters pre-declared.

        The function sees the enclosing scope's declarations, skipping any class
        bodies in between, and the enum names bound so far.
        """
        parameters: set[str] = set()
        arg: ast.arg
        for arg in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]:
            parameters.add(arg.arg)
        if node.args.vararg is not None:
            parameters.add(node.args.vararg.arg)
        if node.args.kwarg is not None:
            parameters.add(node.args.kwarg.arg)

        inner: ScopeChecker = self._nested(self.visible_to_functions | parameters)
        body: list[ast.stmt] | ast.expr = node.body
        if isinstance(body, list):
            inner.visit_body(body)
        else:
            inner.visit(body)
        self.violations.extend(inner.violations)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """A def binds its own name and opens a new scope."""
        self.declared.add(node.name)
        self._enter_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Async defs bind a name and open a scope, same as sync defs."""
        self.declared.add(node.name)
        self._enter_function(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:  # passthrough: allow -- NodeVisitor dispatches by name
        """Lambdas open a scope with no statements to check."""
        self._enter_function(node)

    def _declared_attributes(self, node: ast.ClassDef) -> set[str]:
        """Collect class-body annotations, including those of in-file base classes.

        Dataclass and Pydantic fields are ordinary class-body annotations, so they
        are picked up here without special-casing either library.
        """
        attributes: set[str] = set()
        base: ast.expr
        for base in node.bases:
            if isinstance(base, ast.Name):
                attributes |= self.class_attributes.get(base.id, set())
        statement: ast.stmt
        for statement in node.body:
            if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
                attributes.add(statement.target.id)
        return attributes

    def _nested(self, declared: set[str]) -> ScopeChecker:
        """Return a checker for a scope nested in this one, which sees the imports and enum classes bound so far."""
        inner: ScopeChecker = ScopeChecker(self.path, declared, self.enum_bases, self.package)
        inner.imports = dict(self.imports)
        inner.enum_classes = set(self.enum_classes)
        return inner

    def _qualified_name(self, node: ast.expr) -> str | None:
        """Return the fully qualified name an expression refers to through this scope's imports, or None."""
        if isinstance(node, ast.Attribute):
            owner: str | None = self._qualified_name(node.value)
            return None if owner is None else f"{owner}.{node.attr}"
        if isinstance(node, ast.Name):
            return self.imports.get(node.id)
        return None

    def _is_enum_base(self, base: ast.expr) -> bool:
        """Return whether a base class expression resolves to an enum class in this scope."""
        if isinstance(base, ast.Name) and base.id in self.enum_classes:
            return True
        return self._qualified_name(base) in self.enum_bases

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """A class binds its own name, opens a scope, and declares its attributes; an enum also exempts its members."""
        self.declared.add(node.name)
        attributes: set[str] = self._declared_attributes(node)
        self.class_attributes[node.name] = attributes

        method: ast.stmt
        for method in node.body:
            if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)) and method.args.args:
                receiver: str = method.args.args[0].arg
                attribute_checker: AttributeChecker = AttributeChecker(self.path, receiver, set(attributes))
                body_statement: ast.stmt
                for body_statement in method.body:
                    attribute_checker.visit(body_statement)
                self.violations.extend(attribute_checker.violations)

        is_enum: bool = any(self._is_enum_base(base) for base in node.bases)
        # A violation in a class with an imported base may be an enum member whose
        # base is defined elsewhere; say how to list it.
        imported_bases: list[str] = [] if is_enum else [name for name in map(self._qualified_name, node.bases) if name is not None]
        self.imports.pop(node.name, None)
        if is_enum:
            self.enum_classes.add(node.name)
        else:
            self.enum_classes.discard(node.name)

        inner: ScopeChecker = self._nested(self.visible_to_functions)
        inner.class_attributes = self.class_attributes
        inner.in_enum_body = is_enum
        if imported_bases:
            inner.member_hint = f"if {' or '.join(imported_bases)} is an enum, list it in enum-bases under [tool.check-declarations] in pyproject.toml"
        inner.visible_to_functions = self.visible_to_functions
        inner.visit_body(node.body)
        self.violations.extend(inner.violations)

    def visit_body(self, body: list[ast.stmt]) -> None:
        """Visit statements in source order so declarations precede bindings."""
        statement: ast.stmt
        for statement in body:
            self.visit(statement)


def _is_member_target(node: ast.expr) -> bool:
    """Return whether an assignment target in an enum body binds only members: a name, or a tuple or list of them."""
    if isinstance(node, (ast.Tuple, ast.List)):
        return all(_is_member_target(element) for element in node.elts)
    return isinstance(node, ast.Name)


def _sub_patterns(node: ast.pattern) -> list[ast.pattern]:
    """Return a structural pattern's direct sub-patterns, in source order."""
    if isinstance(node, ast.MatchAs):
        return [] if node.pattern is None else [node.pattern]
    if isinstance(node, (ast.MatchMapping, ast.MatchSequence, ast.MatchOr)):
        return list(node.patterns)
    if isinstance(node, ast.MatchClass):
        return [*node.patterns, *node.kwd_patterns]
    return []


def _pattern_target(node: ast.pattern) -> ast.Name | None:
    """Return the name a pattern binds itself, apart from its sub-patterns, as a reportable node."""
    if isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name is not None:
        return ast.Name(id=node.name, lineno=node.lineno, col_offset=node.col_offset)
    if isinstance(node, ast.MatchMapping) and node.rest is not None:
        # ``**rest`` has no AST node of its own; report it at the end of
        # the mapping so it sorts after the keys it follows in source.
        return ast.Name(id=node.rest, lineno=node.end_lineno or node.lineno, col_offset=node.end_col_offset or node.col_offset)
    return None


def check_source(path: Path, source: str, enum_bases: frozenset[str] = _STDLIB_ENUM_BASES, package: str = "") -> list[Violation]:
    """Return every declaration violation in one module.

    Args:
        path: File path, used for reporting.
        source: Module source text.
        enum_bases: Fully qualified names of the enum base classes to recognize.
        package: The module's package, against which relative imports resolve.

    Returns:
        Violations in source order.
    """
    tree: ast.Module = ast.parse(source, filename=str(path))
    checker: ScopeChecker = ScopeChecker(path, set(), enum_bases, package)
    checker.visit_body(tree.body)
    return sorted(checker.violations, key=lambda item: (item.line, item.column))


def read_source(path: Path) -> str:
    """Return parseable Python source for a module or notebook.

    Notebook code cells are concatenated so bindings in an earlier cell declare
    names used in a later one, matching how the notebook actually executes.

    Args:
        path: A ``.py`` or ``.ipynb`` file.

    Returns:
        Source text ready for ``ast.parse``.
    """
    text: str = path.read_text(encoding="utf-8")
    if path.suffix != ".ipynb":
        return text

    document: dict[str, object] = json.loads(text)
    cells: object = document.get("cells")
    if not isinstance(cells, list):
        return ""
    return "\n".join(_cell_code(cell) for cell in cells if isinstance(cell, dict) and cell.get("cell_type") == "code")


def _cell_code(cell: dict[str, object]) -> str:
    """Return one notebook code cell's source, without IPython magics or shell escapes."""
    lines: object = cell.get("source", "")
    joined: str = "".join(lines) if isinstance(lines, list) else str(lines)
    return "\n".join(line for line in joined.splitlines() if not line.lstrip().startswith(("%", "!")))


def package_of(path: Path) -> str:
    """Return the dotted package a module belongs to, from the ``__init__.py`` files above it."""
    parts: list[str] = []
    directory: Path = path.resolve().parent
    while (directory / "__init__.py").is_file():
        parts.insert(0, directory.name)
        directory = directory.parent
    return ".".join(parts)


def load_enum_bases(pyproject: Path) -> frozenset[str]:
    """Return the standard-library enum bases plus those listed in ``[tool.check-declarations]``.

    Raises:
        ValueError: The file is not valid TOML, or ``enum-bases`` is not a list of strings.
    """
    if not pyproject.is_file():
        return _STDLIB_ENUM_BASES
    # PEP 518 makes ``tool`` and its subtables tables, so only the value is checked.
    configured: object = tomllib.loads(pyproject.read_text(encoding="utf-8")).get("tool", {}).get("check-declarations", {}).get("enum-bases", [])
    if not isinstance(configured, list) or not all(isinstance(item, str) for item in configured):
        msg: str = "[tool.check-declarations] enum-bases must be a list of strings"
        raise ValueError(msg)
    return _STDLIB_ENUM_BASES | frozenset(configured)


def iter_python_files(roots: list[Path]) -> Iterator[Path]:
    """Yield every Python file or notebook under the given files or directories."""
    root: Path
    for root in roots:
        if root.is_file():
            yield root
        else:
            pattern: str
            for pattern in ("*.py", "*.ipynb"):
                yield from sorted(root.rglob(pattern))


def main(argv: list[str] | None = None, pyproject: Path = PYPROJECT) -> int:
    """Run the checker over the given paths.

    Args:
        argv: Command-line arguments, defaulting to ``sys.argv[1:]``.
        pyproject: The project file that may list further enum bases.

    Returns:
        1 when any violation is found or the project file is malformed, otherwise 0.
    """
    parser: argparse.ArgumentParser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    args: argparse.Namespace = parser.parse_args(argv)

    try:
        enum_bases: frozenset[str] = load_enum_bases(pyproject)
    except ValueError as exc:
        print(f"{pyproject}: {exc}", file=sys.stderr)
        return 1

    violations: list[Violation] = []
    path: Path
    for path in iter_python_files(args.paths):
        try:
            violations.extend(check_source(path, read_source(path), enum_bases, package_of(path)))
        except SyntaxError as exc:
            print(f"{path}:{exc.lineno}:{exc.offset}: could not parse: {exc.msg}", file=sys.stderr)
            return 1

    violation: Violation
    for violation in violations:
        print(violation.render())

    if violations:
        print(f"\n{len(violations)} declaration violation(s)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
PYEOF

# --------------------------------------------------------------------------- #
# tools/__init__.py  and  tests/.gitkeep
# --------------------------------------------------------------------------- #

write_file tools/__init__.py <<'INIT'
"""Repository tooling that runs under uv, not shipped with the package."""
INIT

write_file tests/.gitkeep </dev/null

# --------------------------------------------------------------------------- #
# Change-scoped checks -- kept byte-identical to skill/ by tests/test_setup_script.py.
# check_suppressions.py fails on an added suppression not approved in
# suppressions.toml; check_coverage_records.py (CI) fails on a changed module
# with no coverage record. Both share tools/changes.py and run as modules.
# --------------------------------------------------------------------------- #

write_file tools/changes.py <<'CHANGESEOF'
"""Git helpers for checks that look only at what a change adds.

Commands go through the Stop hook's runner, so output is decoded as UTF-8 and
every git failure raises ``GitError``: the checks fail closed rather than read a
broken repository as "nothing changed".
"""

from __future__ import annotations

import re
from collections.abc import Callable

from .hooks.stop_gate import GitError, Result, Runner, git_paths

HUNK: re.Pattern[str] = re.compile(r"^@@ -\S+ \+(\d+)")


def base_commit(base: str | None, run: Runner) -> str:
    """Return the commit to compare against: ``HEAD``, or the merge base with ``base``.

    The merge base, not ``base`` itself, so commits the base branch gained after
    this branch forked are not counted as this branch's changes. Before the first
    commit there is no ``HEAD``; the result is then "", meaning every line is new.
    ``rev-parse --verify --quiet`` exits 1 for that case alone; any other failure
    (a broken configuration, no repository) raises, so it is never mistaken for it.

    Raises:
        GitError: git failed, or could not find the merge base.
    """
    command: tuple[str, ...]
    result: Result
    if base is None:
        command = ("git", "rev-parse", "--verify", "--quiet", "HEAD")
        result = run(command)
        if result.returncode in {0, 1}:
            return "HEAD" if result.returncode == 0 else ""
        raise GitError(command, result)
    command = ("git", "merge-base", base, "HEAD")
    result = run(command)
    if result.returncode != 0:
        raise GitError(command, result)
    return result.output.strip()


def changed_files(commit: str, run: Runner) -> list[str]:
    """Return the files changed since ``commit`` that still exist, sorted."""
    return sorted(git_paths(("git", "diff", "-z", "--name-only", "--relative", "--diff-filter=d", commit), run))


def added_lines(path: str, commit: str, run: Runner, read: Callable[[str], str]) -> list[tuple[int, str]]:
    """Return the ``(line number, text)`` pairs added to ``path`` since ``commit``.

    Every line is added when there is no commit yet (``commit`` is "") or the file
    is untracked; git has no diff for either.
    """
    if not commit or git_paths(("git", "ls-files", "-z", "--others", "--exclude-standard", "--", path), run):
        return list(enumerate(read(path).splitlines(), start=1))
    command: tuple[str, ...] = ("git", "diff", "-U0", "--no-color", "--no-ext-diff", commit, "--", path)
    result: Result = run(command)
    if result.returncode != 0:
        raise GitError(command, result)
    added: list[tuple[int, str]] = []
    number: int = 0
    line: str
    for line in result.output.splitlines():
        hunk: re.Match[str] | None = HUNK.match(line)
        if hunk is not None:
            number = int(hunk.group(1))
        elif line.startswith("+") and not line.startswith("+++"):
            added.append((number, line[1:]))
            number += 1
    return added
CHANGESEOF

write_file tools/check_suppressions.py <<'SUPPRESSEOF'
"""Fail when a change adds a suppression the user has not approved.

Suppressing a lint, type, or coverage finding needs the user's explicit
authorization. This makes that rule mechanical: a ``noqa``, ``type: ignore``,
``pyright: ignore``, ``pragma: no cover``, or ``pragma: no branch`` comment on an
added line fails, as does a file- or function-level one (``ruff: noqa``,
``flake8: noqa``, ``mypy:`` and ``pyright:`` settings, ``complexipy: ignore``,
``passthrough: allow``), unless ``suppressions.toml`` lists its file and code
(for a setting, its whole value):

    [[suppression]]
    path = "tools/hooks/stop_gate.py"
    code = "S603"
    reason = "argv comes from a fixed list, never a shell"

The guard hook protects ``suppressions.toml``, so an agent adding an entry
triggers the user's permission prompt; that prompt is the approval. A blanket
suppression has no code and can never be approved. One exception is built in:
unit tests may suppress Pyright's ``reportPrivateUsage`` per line.

Only added lines count, so existing suppressions never block an unrelated edit.

Usage:
    uv run python -m tools.check_suppressions <files>         (pre-commit: added since HEAD)
    uv run python -m tools.check_suppressions --base origin/main   (CI: added on this branch)
Exit status is 1 when any unapproved suppression is found or git fails.
"""

from __future__ import annotations

import argparse
import io
import re
import tokenize
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .changes import added_lines, base_commit, changed_files
from .hooks.stop_gate import PYTHON_SUFFIXES, GitError, Runner, run_command

ALLOW_LIST: Path = Path("suppressions.toml")
REQUIRED_KEYS: tuple[str, ...] = ("path", "code", "reason")
# Line-level directives, then the file- and function-level ones (ruff and flake8
# file noqa, mypy and pyright file comments, complexipy's ignore, check_passthrough's
# allow), which silence more than a line. coverage.py honors "no cover" and "no
# branch" pragmas, and mutmut skips lines marked "no mutate".
DIRECTIVE: re.Pattern[str] = re.compile(
    r"#\s*(ruff:\s*noqa|flake8:\s*noqa|noqa|type:\s*ignore|pyright:\s*ignore|pyright:|mypy:|complexipy:\s*ignore|passthrough:\s*allow|pragma:?\s*no\s*(?:cover|branch|mutate))", re.IGNORECASE
)
# Ruff separates noqa codes with commas, spaces, or both; every code is captured.
NOQA_CODES: re.Pattern[str] = re.compile(r":\s*([A-Z]+[0-9]+(?:[\s,]+[A-Z]+[0-9]+)*)")
CODE: re.Pattern[str] = re.compile(r"[A-Z]+[0-9]+")
# Each directive by its letters alone, so "type:ignore", "type: ignore", and
# "pragma no cover" classify the same way their tools read them.
CANONICAL: dict[str, str] = {
    "ruffnoqa": "ruff: noqa",
    "flake8noqa": "flake8: noqa",
    "noqa": "noqa",
    "typeignore": "type: ignore",
    "pyrightignore": "pyright: ignore",
    "pyright": "pyright:",
    "mypy": "mypy:",
    "complexipyignore": "complexipy: ignore",
    "passthroughallow": "passthrough: allow",
    "pragmanocover": "pragma: no cover",
    "pragmanobranch": "pragma: no branch",
    "pragmanomutate": "pragma: no mutate",
}
NOQA_KINDS: frozenset[str] = frozenset({"noqa", "ruff: noqa", "flake8: noqa"})
BRACKETED_RULES: re.Pattern[str] = re.compile(r"\[([^\]]*)\]")


@dataclass(frozen=True)
class Suppression:
    """One suppressed code; a comment naming several codes yields one each."""

    kind: str
    code: str

    def label(self) -> str:
        """Return the suppression as it reads in source."""
        if self.kind in NOQA_KINDS:
            return f"{self.kind}: {self.code}" if self.code else f"{self.kind} ({'blanket' if self.kind == 'noqa' else 'whole file'})"
        if self.kind in {"pragma", "complexipy", "passthrough", "mypy", "pyright"}:
            return f"{self.kind}: {self.code}"
        return f"{self.kind}[{self.code}]" if self.code else self.kind


@dataclass(frozen=True)
class Allowed:
    """The approved ``(path, code)`` pairs from the allow-list."""

    pairs: set[tuple[str, str]]

    def permits(self, path: str, suppression: Suppression) -> bool:
        """Return whether this suppression in this file is approved."""
        if suppression.kind == "pyright: ignore" and suppression.code == "reportPrivateUsage" and is_test(path):
            return True
        return bool(suppression.code) and (path, suppression.code) in self.pairs


def is_test(path: str) -> bool:
    """Return whether a path names a unit-test file."""
    normalized: str = "/" + path.replace("\\", "/")
    return "/tests/" in normalized or normalized.rpartition("/")[2].startswith("test_")


def suppressions_in(line: str) -> list[Suppression]:
    """Return every suppression a source line carries, one per code."""
    found: list[Suppression] = []
    directive: re.Match[str]
    for directive in DIRECTIVE.finditer(line):
        found.extend(parse_directive(CANONICAL[re.sub(r"[\s:]", "", directive.group(1).lower())], line[directive.end() :]))
    return found


def parse_directive(word: str, tail: str) -> list[Suppression]:
    """Return the suppressions one directive carries, given its normalized word and the text after it."""
    if word in NOQA_KINDS:
        codes: re.Match[str] | None = NOQA_CODES.match(tail)
        return [Suppression(word, code) for code in (CODE.findall(codes.group(1)) if codes else [""])]
    if word in {"type: ignore", "pyright: ignore"}:
        rules: re.Match[str] | None = BRACKETED_RULES.match(tail)
        return [Suppression(word, rule.strip()) for rule in (rules.group(1).split(",") if rules else [""])]
    if word in {"pyright:", "mypy:"}:
        # The whole setting is the code, so approving one value never approves another.
        return [Suppression(word.removesuffix(":"), " ".join(tail.split()))]
    if word == "complexipy: ignore":
        return [Suppression("complexipy", "ignore")]
    if word == "passthrough: allow":
        return [Suppression("passthrough", "allow")]
    return [Suppression("pragma", word.removeprefix("pragma: "))]


def load_allowed(path: Path) -> Allowed:
    """Read the allow-list; a missing file approves nothing.

    Raises:
        ValueError: an entry lacks a non-empty path, code, or reason.
    """
    if not path.exists():
        return Allowed(set())
    return allowed_from_text(path.read_text(encoding="utf-8"), str(path))


def allowed_from_text(text: str, source: str) -> Allowed:
    """Parse allow-list text; ``source`` names it in error messages.

    Raises:
        ValueError: an entry lacks a non-empty path, code, or reason.
    """
    entries: object = tomllib.loads(text).get("suppression")
    pairs: set[tuple[str, str]] = set()
    index: int
    entry: object
    for index, entry in enumerate(entries if isinstance(entries, list) else [], start=1):
        fields: list[object] = [entry.get(key) for key in REQUIRED_KEYS] if isinstance(entry, dict) else []
        if not fields or not all(isinstance(field, str) and field.strip() for field in fields):
            message: str = f"{source}: [[suppression]] entry {index} needs a non-empty path, code, and reason"
            raise ValueError(message)
        pairs.add((str(fields[0]), str(fields[1])))
    return Allowed(pairs)


def read_file(path: str) -> str:
    """Return a file's text."""
    return Path(path).read_text(encoding="utf-8")


def main(argv: list[str] | None = None, run: Runner = run_command, read: Callable[[str], str] = read_file, allow_list: Path = ALLOW_LIST) -> int:
    """Report every unapproved suppression the change adds.

    Args:
        argv: Command-line arguments, defaulting to ``sys.argv[1:]``.
        run: Executes git; replaced by a fake in tests.
        read: Returns a file's text; replaced in tests.
        allow_list: The approved suppressions.

    Returns:
        1 when any unapproved suppression is found or git fails, otherwise 0.
    """
    parser: argparse.ArgumentParser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", default=None, help="compare against the merge base with this ref instead of HEAD")
    parser.add_argument("files", nargs="*", help="files to check; default: every file changed since --base")
    args: argparse.Namespace = parser.parse_args(argv)
    findings: list[str]
    try:
        allowed: Allowed = load_allowed(allow_list)
        commit: str = base_commit(args.base, run)
        files: list[str] = args.files or changed_files(commit, run)
        findings = unapproved(files, commit, run, read, allowed)
    except GitError as error:
        print(f"`{' '.join(error.command)}` failed, so the change cannot be checked:\n{error.result.output}")
        return 1
    except ValueError as error:
        print(error)
        return 1
    finding: str
    for finding in findings:
        print(finding)
    return 1 if findings else 0


def unapproved(files: list[str], commit: str, run: Runner, read: Callable[[str], str], allowed: Allowed) -> list[str]:
    """Return one message per unapproved suppression on an added line of a Python file.

    In a module only real comments are scanned, so directive text inside a string
    or docstring is not a suppression. A notebook (JSON) or a module Python cannot
    tokenize (mid-edit) is scanned as text, which errs toward reporting.
    """
    findings: list[str] = []
    path: str
    for path in files:
        if not path.endswith(PYTHON_SUFFIXES):
            continue
        lines: list[tuple[int, str]] = added_lines(path, commit, run, read)
        comments: dict[int, str] | None = comments_by_line(read(path)) if lines and path.endswith(".py") else None
        number: int
        text: str
        for number, text in lines:
            findings.extend(
                f"{path}:{number}: new suppression `{suppression.label()}` needs the user's approval. Fix the code instead, or ask the user to approve a [[suppression]] entry (path, code, reason) in suppressions.toml."
                for suppression in suppressions_in(text if comments is None else comments.get(number, ""))
                if not allowed.permits(path, suppression)
            )
    return findings


def comments_by_line(source: str) -> dict[int, str] | None:
    """Return each line's comment text by line number, or None when the source cannot be tokenized."""
    try:
        return {token.start[0]: token.string for token in tokenize.generate_tokens(io.StringIO(source).readline) if token.type == tokenize.COMMENT}
    except (tokenize.TokenError, SyntaxError):
        return None


if __name__ == "__main__":
    raise SystemExit(main())
SUPPRESSEOF

write_file tools/check_coverage_records.py <<'COVRECEOF'
"""CI: fail when a Python module changed on this branch has no coverage record.

A module no test imports is never recorded in ``coverage.xml``, and diff-cover
silently skips files without a record, so an entirely untested new module
would pass the 100%-of-changed-lines gate. This closes that gap with the same
check the Stop hook runs locally (``unrecorded_modules``), which also fails a
module whose record another coverage source's same-named file could own.
Notebooks are exempt: pytest-cov never measures them.

Usage, after the test step has written coverage.xml:
    uv run python -m tools.check_coverage_records --base origin/main
Exit status is 1 when a changed module has no record or git fails.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path

from .changes import base_commit, changed_files
from .hooks.stop_gate import AMBIGUOUS_RECORD, COVERAGE_XML, GitError, MissingRecords, Runner, read_coverage_xml, run_command, unrecorded_modules


def main(argv: list[str] | None = None, run: Runner = run_command, read_coverage: Callable[[Path], str] = read_coverage_xml) -> int:
    """Report every module changed since the merge base that coverage.xml does not record.

    Args:
        argv: Command-line arguments, defaulting to ``sys.argv[1:]``.
        run: Executes git; replaced by a fake in tests.
        read_coverage: Returns a coverage report's text; replaced in tests.

    Returns:
        1 when a changed module has no attributable coverage record or git fails, otherwise 0.
    """
    parser: argparse.ArgumentParser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", required=True, help="the branch's base ref, e.g. origin/main")
    parser.add_argument("--coverage", type=Path, default=COVERAGE_XML, help="the Cobertura report pytest-cov wrote")
    args: argparse.Namespace = parser.parse_args(argv)
    files: list[str]
    try:
        files = changed_files(base_commit(args.base, run), run)
    except GitError as error:
        print(f"`{' '.join(error.command)}` failed, so the change cannot be checked:\n{error.result.output}")
        return 1
    missing: MissingRecords = unrecorded_modules(files, read_coverage(args.coverage), Path.cwd())
    path: str
    for path in missing.untested:
        print(f"{path}: no coverage record. No test imports this module, so none of its lines are measured and diff-cover skips it. Add a test that exercises it.")
    for path in missing.ambiguous:
        print(f"{path}: coverage record cannot be attributed. {AMBIGUOUS_RECORD}")
    return 1 if missing.untested or missing.ambiguous else 0


if __name__ == "__main__":
    raise SystemExit(main())
COVRECEOF

write_file tools/review_brief.py <<'BRIEFEOF'
"""Print a one-screen brief that says where a reviewer should look in a change.

Every section is computed, not judged: the change's size, gate files it touches,
dependency changes, suppressions it adds (approved or not), the most complex
changed functions, changed modules no test imports, and surviving mutants in
changed modules. An empty section says so, so a brief of "none"s means nothing
needs a closer look.

The Stop hook shows it to the user after every turn whose changes pass the gates.

Usage:
    uv run python -m tools.review_brief                    (working tree against HEAD)
    uv run python -m tools.review_brief --base origin/main (this branch's changes)
Exit status is 1 when git fails, otherwise 0.
"""

from __future__ import annotations

import argparse
import json
import tomllib
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .changes import added_lines, base_commit
from .check_suppressions import Allowed, allowed_from_text, comments_by_line, suppressions_in
from .hooks.guard_protected import is_protected
from .hooks.stop_gate import AMBIGUOUS_RECORD, PYTHON_SUFFIXES, GitError, MissingRecords, Result, Runner, git_paths, run_command, unrecorded_modules

COMPLEXITY_REPORT: str = ".complexipy_cache/review-brief.json"
DEFAULT_COMPLEXITY_CAP: int = 15
TOP_FUNCTIONS: int = 5


@dataclass(frozen=True)
class FileChange:
    """One changed file: lines added and removed, or binary."""

    path: str
    added: int
    removed: int
    binary: bool = False
    untracked: bool = False


def read_text(path: str) -> str:
    """Return a file's text, replacing bytes that are not UTF-8."""
    return Path(path).read_text(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None, run: Runner = run_command, read: Callable[[str], str] = read_text) -> int:
    """Print the brief for the working tree, or for the branch with ``--base``.

    Args:
        argv: Command-line arguments, defaulting to ``sys.argv[1:]``.
        run: Executes git and complexipy; replaced by a fake in tests.
        read: Returns a file's text and raises ``FileNotFoundError`` for a missing one; replaced in tests.

    Returns:
        1 when git fails, otherwise 0.
    """
    parser: argparse.ArgumentParser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", help="describe the changes since the merge base with this ref instead of HEAD")
    args: argparse.Namespace = parser.parse_args(argv)
    try:
        print(build_brief(args.base, run, read))
    except GitError as error:
        print(f"`{' '.join(error.command)}` failed, so there is no brief:\n{error.result.output}")
        return 1
    return 0


def build_brief(base: str | None, run: Runner, read: Callable[[str], str]) -> str:
    """Return the brief as Markdown."""
    commit: str = base_commit(base, run)
    since: str = base or "HEAD"
    changes: list[FileChange] = file_changes(commit, run, read)
    if not changes:
        return f"Review brief: no changes since {since}."
    sources: dict[str, str] = readable_python(changes, read)
    sections: list[str] = [
        size_section(changes),
        gates_section(changes),
        dependencies_section(changes, commit, run, read),
        suppressions_section(sources, commit, run, read),
        complexity_section(sources, run, read),
        coverage_section(sources, read),
        mutation_section(sources, read),
    ]
    return "\n\n".join([f"# Review brief: changes since {since}", *sections])


def file_changes(commit: str, run: Runner, read: Callable[[str], str]) -> list[FileChange]:
    """Return the tracked changes since ``commit`` and the untracked files, in path order."""
    changes: list[FileChange] = []
    new_paths: set[str]
    if commit:
        changes = numstat(commit, run)
        new_paths = git_paths(("git", "ls-files", "-z", "--others", "--exclude-standard"), run)
    else:
        new_paths = git_paths(("git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"), run)
    path: str
    for path in new_paths:
        changes.append(FileChange(path, len(read(path).splitlines()), 0, untracked=True))
    return sorted(changes, key=lambda change: change.path)


def numstat(commit: str, run: Runner) -> list[FileChange]:
    """Return ``git diff --numstat`` against ``commit``: tracked files, staged or not."""
    command: tuple[str, ...] = ("git", "diff", "-z", "--numstat", "--no-renames", "--relative", commit)
    result: Result = run(command)
    if result.returncode != 0:
        raise GitError(command, result)
    changes: list[FileChange] = []
    entry: str
    for entry in result.output.split("\0"):
        if entry:
            added: str
            removed: str
            path: str
            added, removed, path = entry.split("\t", 2)
            binary: bool = added == "-"
            changes.append(FileChange(path, 0 if binary else int(added), 0 if binary else int(removed), binary=binary))
    return changes


def readable_python(changes: list[FileChange], read: Callable[[str], str]) -> dict[str, str]:
    """Return the text of each changed Python file that still exists."""
    sources: dict[str, str] = {}
    change: FileChange
    for change in changes:
        if change.path.endswith(PYTHON_SUFFIXES):
            try:
                sources[change.path] = read(change.path)
            except FileNotFoundError:
                continue
    return sources


def size_section(changes: list[FileChange]) -> str:
    """Return the size section: every file with its lines added and removed."""
    lines: list[str] = [f"## Size: {len(changes)} files, +{sum(change.added for change in changes)} / -{sum(change.removed for change in changes)}"]
    change: FileChange
    for change in changes:
        if change.binary:
            lines.append(f"- `{change.path}` binary")
        else:
            lines.append(f"- `{change.path}` +{change.added} / -{change.removed}" + (" (new, untracked)" if change.untracked else ""))
    return "\n".join(lines)


def gates_section(changes: list[FileChange]) -> str:
    """Return the changed files that define a quality gate; they always need a human look."""
    gates: list[str] = [change.path for change in changes if is_protected(change.path)]
    if not gates:
        return "## Gate files touched: none"
    return "\n".join([f"## Gate files touched: {len(gates)}", *(f"- `{path}`" for path in gates)])


def dependencies_section(changes: list[FileChange], commit: str, run: Runner, read: Callable[[str], str]) -> str:
    """Return the requirements added to or removed from ``pyproject.toml``."""
    if "pyproject.toml" not in {change.path for change in changes}:
        return "## Dependencies: no change"
    before_result: Result = run(("git", "show", f"{commit}:./pyproject.toml"))
    before: set[str] = requirements(before_result.output) if commit and before_result.returncode == 0 else set()
    try:
        after: set[str] = requirements(read("pyproject.toml"))
    except FileNotFoundError:
        after = set()
    added: list[str] = sorted(after - before)
    removed: list[str] = sorted(before - after)
    if not added and not removed:
        return "## Dependencies: no change"
    return "\n".join([f"## Dependencies: +{len(added)} / -{len(removed)}", *(f"- added `{item}`" for item in added), *(f"- removed `{item}`" for item in removed)])


def requirements(text: str) -> set[str]:
    """Return every requirement in ``[project] dependencies`` and ``[dependency-groups]``."""
    document: dict[str, object] = tomllib.loads(text)
    found: set[str] = set()
    project: object = document.get("project")
    if isinstance(project, dict):
        found.update(str(item) for item in project.get("dependencies", []))
    groups: object = document.get("dependency-groups")
    if isinstance(groups, dict):
        group: object
        for group in groups.values():
            if isinstance(group, list):
                found.update(str(item) for item in group if isinstance(item, str))
    return found


def suppressions_section(sources: dict[str, str], commit: str, run: Runner, read: Callable[[str], str]) -> str:
    """Return the suppressions the change adds, unapproved ones first."""
    try:
        allowed: Allowed = allowed_from_text(read("suppressions.toml"), "suppressions.toml")
    except (FileNotFoundError, ValueError):
        allowed = Allowed(set())
    found: list[tuple[bool, str, int, str]] = []
    path: str
    source: str
    for path, source in sources.items():
        found.extend(added_suppressions(path, source, added_lines(path, commit, run, read), allowed))
    if not found:
        return "## Suppressions added: none"
    found.sort()
    unapproved: int = sum(1 for approved, *_ in found if not approved)
    lines: list[str] = [f"## Suppressions added: {len(found)} ({unapproved} unapproved)"]
    lines.extend(f"- `{path}:{number}` `{label}` {'approved' if approved else 'UNAPPROVED'}" for approved, path, number, label in found)
    return "\n".join(lines)


def added_suppressions(path: str, source: str, lines: list[tuple[int, str]], allowed: Allowed) -> list[tuple[bool, str, int, str]]:
    """Return ``(approved, path, line, label)`` for each suppression on one file's added lines."""
    comments: dict[int, str] | None = comments_by_line(source) if path.endswith(".py") else None
    return [(allowed.permits(path, suppression), path, number, suppression.label()) for number, text in lines for suppression in suppressions_in(text if comments is None else comments.get(number, ""))]


def complexity_section(sources: dict[str, str], run: Runner, read: Callable[[str], str]) -> str:
    """Return the most complex functions in the changed modules, against the cap."""
    modules: list[str] = sorted(path for path in sources if path.endswith(".py"))
    if not modules:
        return "## Complexity: no changed Python modules"
    # --ignore-complexity: complexipy otherwise exits 1 on an over-cap function, which is
    # exactly the function the reviewer needs to see; a non-zero exit then means it failed.
    if run(("uv", "run", "--no-sync", "complexipy", "--ignore-complexity", "--output-format", "json", "--output", COMPLEXITY_REPORT, *modules)).returncode != 0:
        return "## Complexity: not measured (complexipy did not run)"
    report: list[dict[str, object]] = json.loads(read(COMPLEXITY_REPORT))
    scored: list[tuple[int, str, str]] = sorted(
        ((int(str(entry["complexity"])), str(entry["path"]).replace("\\", "/"), str(entry["function_name"])) for entry in report if str(entry["path"]).replace("\\", "/") in sources),
        key=lambda item: (-item[0], item[1], item[2]),
    )
    lines: list[str] = [f"## Complexity: highest in changed files (cap {complexity_cap(read)})"]
    lines.extend(f"- `{path}` `{name}` {score}" for score, path, name in scored[:TOP_FUNCTIONS])
    return "\n".join(lines)


def complexity_cap(read: Callable[[str], str]) -> int:
    """Return complexipy's configured cap, or its documented default."""
    try:
        settings: object = tomllib.loads(read("pyproject.toml")).get("tool", {}).get("complexipy")
    except FileNotFoundError:
        return DEFAULT_COMPLEXITY_CAP
    cap: object = settings.get("max-complexity-allowed") if isinstance(settings, dict) else None
    return cap if isinstance(cap, int) else DEFAULT_COMPLEXITY_CAP


def coverage_section(sources: dict[str, str], read: Callable[[str], str]) -> str:
    """Return the changed modules that coverage.xml has no record of."""
    try:
        report: str = read("coverage.xml")
    except FileNotFoundError:
        return "## Coverage: no coverage.xml (run the tests with --cov)"
    missing: MissingRecords = unrecorded_modules(sorted(sources), report, Path.cwd())
    count: int = len(missing.untested) + len(missing.ambiguous)
    if not count:
        return "## Coverage: every changed module has a coverage record"
    noun: str = "module" if count == 1 else "modules"
    return "\n".join(
        [
            f"## Coverage: {count} changed {noun} without a coverage record",
            *(f"- `{path}`" for path in missing.untested),
            *(f"- `{path}`: {AMBIGUOUS_RECORD}" for path in missing.ambiguous),
        ]
    )


def mutation_section(sources: dict[str, str], read: Callable[[str], str]) -> str:
    """Return the surviving mutants, from the last mutation run, in the changed modules."""
    try:
        survivors: str = read("mutants/survivors.txt")
    except FileNotFoundError:
        return "## Mutation: no mutants/survivors.txt (run bash tools/mutation.sh)"
    counts: Counter[str] = Counter()
    line: str
    for line in survivors.splitlines():
        # mutmut results lists every mutant not killed; a timeout was caught, so count survivors only.
        if not line.rstrip().endswith(": survived"):
            continue
        # "pkg.mod.x_func__mutmut_3: survived" or "pkg.mod.xǁClassǁmethod__mutmut_3: survived".
        # The mangled name is the last segment, and a module may itself be named x_….
        method: tuple[str, str, str] = line.strip().partition(".xǁ")
        module: str = method[0] if method[1] else line.strip().rpartition(".x_")[0]
        path: str = module.replace(".", "/") + ".py"
        if path in sources:
            counts[path] += 1
    if not counts:
        return "## Mutation: no survivors in changed modules (from the last mutation run)"
    return "\n".join([f"## Mutation: {counts.total()} survivors in changed modules (from the last mutation run)", *(f"- `{path}` {count}" for path, count in sorted(counts.items()))])


if __name__ == "__main__":
    raise SystemExit(main())
BRIEFEOF

write_file suppressions.toml <<'ALLOWEOF'
# Suppressions the user has approved. tools/check_suppressions.py fails on any
# suppression comment a change adds that is not listed here by file and code.
# The Claude Code guard hook asks the user before this file changes, so a new
# entry is approved at the moment it is written. Every entry needs a reason.

[[suppression]]
path = "tools/hooks/stop_gate.py"
code = "S603"
reason = "subprocess argv comes from the hook's fixed gate list, never a shell"

[[suppression]]
path = "tools/check_declarations.py"
code = "arg-type"
reason = "the async visitors reuse the sync ones; async nodes carry the same fields"

[[suppression]]
path = "tools/check_declarations.py"
code = "allow"
reason = "NodeVisitor dispatches by method name, so the async and lambda visitors must exist"
ALLOWEOF

# --------------------------------------------------------------------------- #
# Mutation testing -- report-only, nightly in CI and on demand. Kept
# byte-identical to skill/ by tests/test_setup_script.py.
# --------------------------------------------------------------------------- #

write_file tools/mutation.sh <<'MUTEOF'
#!/usr/bin/env bash
#
# mutation.sh -- run mutation testing (mutmut) and list the surviving mutants.
#
# A surviving mutant is a change to the code that no test noticed: the line ran,
# but nothing checked its result. Report-only: survivors never fail this script;
# mutmut errors do.
#
# Run it through bash: setup writes it without the executable bit, and commits
# made on Windows never record one.
#   bash tools/mutation.sh
# mutmut needs os.fork, so it runs on Linux and macOS. On Windows, run it in WSL,
# through a login shell, which puts uv's ~/.local/bin on PATH:
#   wsl -e bash -lc "bash tools/mutation.sh"
# Pass a mutant name pattern to narrow a local run:
#   bash tools/mutation.sh 'mypackage.module*'
#
# Results: mutants/mutmut-cicd-stats.json (counts) and mutants/survivors.txt.

set -euo pipefail

# The project root is the nearest directory holding pyproject.toml, which is not
# always the git root.
cd "$(dirname "$0")"
while [ ! -f pyproject.toml ] && [ "$PWD" != / ]; do cd ..; done

# mutmut's own guess uses the checkout folder's name, so it breaks in a clone or a
# CI checkout under another name. Require the code to be listed explicitly.
if ! grep -q '^source_paths *=' pyproject.toml; then
    printf 'mutation.sh: list the code to mutate in pyproject.toml, e.g.\n  [tool.mutmut]\n  source_paths = ["mypackage"]\n' >&2
    exit 2
fi

# Keep the Linux environment outside the checkout: under WSL this folder is shared
# with Windows, and syncing here would replace the Windows .venv.
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-$HOME/.venvs/$(basename "$PWD")}"

uv sync --all-groups --quiet
uv run --no-sync mutmut run "$@"
uv run --no-sync mutmut export-cicd-stats
uv run --no-sync mutmut results | tee mutants/survivors.txt
MUTEOF

write_file .github/workflows/mutation.yml <<'MUTCI'
name: mutation

# Report-only mutation testing. Surviving mutants (code changes no test noticed)
# are listed in the job log and uploaded as an artifact; they never fail the run.
# It takes too long for every push, so it runs nightly and on demand.
on:
  schedule:
    - cron: "17 3 * * *"
  workflow_dispatch:

permissions:
  contents: read

jobs:
  mutation:
    runs-on: ubuntu-latest
    # A cap, not an estimate: raise it if a full run outgrows it.
    timeout-minutes: 120
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false

      - name: Install uv
        uses: astral-sh/setup-uv@68559e99cc807c1eb7e9238fd43a15bba460eec2 # v10.3.3
        with:
          enable-cache: true

      - name: Mutation testing
        run: bash tools/mutation.sh

      - name: Upload survivors
        if: always()
        uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2
        with:
          name: mutation-report
          path: |
            mutants/mutmut-cicd-stats.json
            mutants/survivors.txt
          if-no-files-found: warn
MUTCI

# --------------------------------------------------------------------------- #
# Claude Code hooks -- .claude/settings.json and tools/hooks/, kept
# byte-identical to skill/ by tests/test_setup_script.py in the standards repo.
# guard_protected.py asks before a quality gate is changed; stop_gate.py keeps
# the agent working until the gates pass on its changes.
# --------------------------------------------------------------------------- #

write_file .claude/settings.json <<'SETTINGS'
{
  "$schema": "https://json.schemastore.org/claude-code-settings.json",
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write|MultiEdit|Bash|PowerShell",
        "hooks": [
          {
            "type": "command",
            "command": "uv run --no-sync --project \"$CLAUDE_PROJECT_DIR\" python \"$CLAUDE_PROJECT_DIR/tools/hooks/guard_protected.py\"",
            "powershell": "$root = if ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { git rev-parse --show-toplevel }; uv run --no-sync --project $root python (Join-Path $root 'tools/hooks/guard_protected.py')",
            "timeout": 30
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "cd \"$CLAUDE_PROJECT_DIR\" && uv run --no-sync python tools/hooks/stop_gate.py",
            "powershell": "$root = if ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { git rev-parse --show-toplevel }; Set-Location $root; uv run --no-sync python tools/hooks/stop_gate.py",
            "timeout": 900
          }
        ]
      }
    ]
  }
}
SETTINGS

write_file tools/hooks/__init__.py <<'HOOKSINIT'
"""Claude Code hooks that hold the quality gates on the agent itself."""
HOOKSINIT

write_file tools/hooks/guard_protected.py <<'GUARDEOF'
"""PreToolUse hook: ask the user before a tool call changes a quality gate.

Tool configuration, the pre-commit and CI pipelines, the gate scripts, and the
hook settings decide what "passing" means. An agent that edits them can make a
failing check pass without fixing anything, so each such edit needs the user's
explicit approval. The hook answers "ask" rather than "deny": a legitimate
change is one approval away, an illegitimate one is never silent.

Shell commands are matched by pattern, so the shell check is best effort; CI,
which runs the unmodified gates, remains the backstop.

Usage, from ``.claude/settings.json``, with the hook event JSON on stdin. It runs
in the project environment, whatever the current directory:
    uv run --no-sync --project "$CLAUDE_PROJECT_DIR" python "$CLAUDE_PROJECT_DIR/tools/hooks/guard_protected.py"
Exit status is always 0; the decision is the JSON written to stdout.
"""

from __future__ import annotations

import json
import re
import sys
from typing import TextIO, cast

PROTECTED_NAMES: frozenset[str] = frozenset(
    {
        "pyproject.toml",
        "ruff.toml",
        ".ruff.toml",
        "setup.cfg",
        "mypy.ini",
        "pyrightconfig.json",
        "pytest.ini",
        "tox.ini",
        ".coveragerc",
        ".pre-commit-config.yaml",
        "suppressions.toml",
    }
)
PROTECTED_SUFFIXES: tuple[str, ...] = (
    "/tools/check_declarations.py",
    "/tools/check_suppressions.py",
    "/tools/check_coverage_records.py",
    "/tools/changes.py",
    "/tools/mutation.sh",
    "/tools/review_brief.py",
    "/.claude/settings.json",
    "/.claude/settings.local.json",
)
PROTECTED_DIRECTORIES: tuple[str, ...] = ("/.github/workflows/", "/tools/hooks/")
FILE_TOOLS: frozenset[str] = frozenset({"edit", "write", "multiedit", "apply_patch"})
SHELL_TOOLS: frozenset[str] = frozenset({"bash", "powershell"})
PATH_KEYS: frozenset[str] = frozenset({"file_path", "filepath", "path"})
PATCH_FILE_HEADER: re.Pattern[str] = re.compile(r"^\*\*\* (?:(?:Add|Update|Delete) File|Move to):[ \t]*(.+?)[ \t]*\r?$", re.MULTILINE)

# Every protected file as it can appear in a command. One alternation serves both
# patterns below, so a redirect is checked against exactly the files that are named.
PROTECTED_TARGETS: str = (
    "(?:"
    + "|".join(re.escape(name) for name in sorted(PROTECTED_NAMES))
    + r"|\.github[/\\]workflows|tools[/\\](?:check_declarations|check_suppressions|check_coverage_records|changes|review_brief)\.py|tools[/\\]mutation\.sh|tools[/\\]hooks|\.claude[/\\]settings)"
)
# A protected file named anywhere in a command: a bare name, or a path ending in one.
PROTECTED_IN_COMMAND: re.Pattern[str] = re.compile(r"(?:^|[\s'\"=/\\])" + PROTECTED_TARGETS, re.IGNORECASE)
# Commands that write, move, or delete the files they name. A redirect only
# counts when it targets a protected file, so "2>/dev/null" stays silent.
WRITES_IN_COMMAND: re.Pattern[str] = re.compile(
    r"\bsed\b[^|;&\n]*\s(?:-[a-zA-Z]*i|--in-place)"
    r"|>>?\s*['\"]?[^\s|;&]*" + PROTECTED_TARGETS + r"|\b(?:tee|mv|cp|rm|truncate)\b"
    r"|\bgit\s+(?:checkout|restore)\b"
    r"|\b(?:Set-Content|Add-Content|Out-File|Remove-Item|Move-Item|Copy-Item)\b",
    re.IGNORECASE,
)
DEPENDENCY_CHANGE: re.Pattern[str] = re.compile(r"\buv\s+(?:add|remove)\b|\buv\s+lock\b[^|;&\n]*--upgrade")


def main(stdin: TextIO = sys.stdin, stdout: TextIO = sys.stdout) -> int:
    """Read one PreToolUse event and write an "ask" decision when it changes a gate.

    Args:
        stdin: Source of the hook event JSON.
        stdout: Destination of the decision JSON; nothing is written to allow the call.

    Returns:
        Always 0, so the hook consumer reads the decision from stdout.
    """
    event: dict[str, object] = json.loads(stdin.read())
    tool_input: object = event.get("tool_input", {})
    reason: str | None = protected_reason(str(event.get("tool_name", "")), tool_input)
    if reason is not None:
        copilot_compatible_event: bool = event.get("hook_event_name") == "PreToolUse" and isinstance(event.get("timestamp"), str) and "tool_use_id" not in event
        decision: dict[str, object]
        if copilot_compatible_event:
            decision = {"permissionDecision": "ask", "permissionDecisionReason": reason}
        else:
            decision = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask", "permissionDecisionReason": reason}}
        stdout.write(json.dumps(decision))
    return 0


def protected_reason(tool_name: str, tool_input: object) -> str | None:
    """Return why this tool call needs the user's approval, or None when it does not."""
    name: str = tool_name.casefold()
    if name not in FILE_TOOLS and name not in SHELL_TOOLS:
        return None
    decoded_input: object = decode_input(tool_input)
    if not isinstance(decoded_input, (dict, str)):
        return "This tool input could not be inspected for quality-gate changes, so the user must approve it."
    if name in FILE_TOOLS:
        return file_tool_reason(name, decoded_input)
    return shell_tool_reason(decoded_input)


def file_tool_reason(tool_name: str, tool_input: dict[object, object] | str) -> str | None:
    """Return why a file-tool input needs approval, or None when its targets are ordinary files."""
    if tool_name == "apply_patch":
        tool_input = unwrap_patch(tool_input)
    elif isinstance(tool_input, str):
        return "This file tool input could not be inspected for quality-gate changes, so the user must approve it."
    paths: list[str] | None = target_paths(tool_input)
    if not paths:
        return "This file tool input could not be inspected for quality-gate changes, so the user must approve it."
    path: str
    for path in paths:
        if is_protected(path):
            return f"{path} defines a quality gate. Changing it can make a failing check pass without a fix, so the user must approve. If the goal is a passing check, fix the code instead."
    return None


def shell_tool_reason(tool_input: dict[object, object] | str) -> str | None:
    """Return why a shell-tool input needs approval, or None when its command is safe."""
    if isinstance(tool_input, dict) and "command" not in tool_input:
        return "This shell command could not be inspected for quality-gate changes, so the user must approve it."
    command: object = tool_input.get("command", "") if isinstance(tool_input, dict) else tool_input
    if not isinstance(command, str):
        return "This shell command could not be inspected for quality-gate changes, so the user must approve it."
    return command_reason(command)


def decode_input(tool_input: object) -> object:
    """Parse JSON-encoded tool objects while preserving raw patch and command strings."""
    if isinstance(tool_input, str) and tool_input.lstrip().startswith(("{", "[")):
        try:
            decoded: object = cast("object", json.loads(tool_input))
        except json.JSONDecodeError:
            return tool_input
        else:
            return decoded
    return tool_input


def unwrap_patch(tool_input: dict[object, object] | str) -> dict[object, object] | str:
    """Return the raw patch from an apply_patch input of the form {"input": "<patch>"}, else the input unchanged.

    Only an object whose single key is "input" is unwrapped, so any other shape
    still falls through to the structured checks and asks when it cannot be read.
    """
    if isinstance(tool_input, dict) and tool_input.keys() == {"input"}:
        patch: object = tool_input["input"]
        if isinstance(patch, str):
            return patch
    return tool_input


def target_paths(tool_input: dict[object, object] | str) -> list[str] | None:
    """Return recognized paths from structured tool inputs or file headers in a raw patch.

    Returns:
        The paths, or None when a recognized path key holds an empty or non-string value.
    """
    if isinstance(tool_input, str):
        return [match.group(1).strip() for match in PATCH_FILE_HEADER.finditer(tool_input)]
    paths: list[str] = []
    value: object
    for value in path_values(tool_input):
        if not isinstance(value, str) or not value.strip():
            return None
        paths.append(value)
    return paths


def path_values(tool_input: object) -> list[object]:
    """Return every value stored under a recognized path key, at any depth, without descending into those values."""
    if isinstance(tool_input, list):
        return [value for item in cast("list[object]", tool_input) for value in path_values(item)]
    if not isinstance(tool_input, dict):
        return []
    values: list[object] = []
    key: object
    value: object
    for key, value in cast("dict[object, object]", tool_input).items():
        if isinstance(key, str) and key.casefold() in PATH_KEYS:
            values.append(value)
        else:
            values.extend(path_values(value))
    return values


def is_protected(path: str) -> bool:
    """Return whether a file path, POSIX or Windows, names a protected file.

    Matching ignores case: on Windows and macOS ``PyProject.toml`` *is* the
    protected file. On a case-sensitive filesystem the cost is an extra prompt.
    """
    # The leading "/" anchors the suffix and directory checks for a relative path.
    normalized: str = "/" + path.replace("\\", "/").casefold()
    name: str = normalized.rpartition("/")[2]
    return name in PROTECTED_NAMES or normalized.endswith(PROTECTED_SUFFIXES) or any(directory in normalized for directory in PROTECTED_DIRECTORIES)


def command_reason(command: str) -> str | None:
    """Return why a shell command needs the user's approval, or None when it does not."""
    if DEPENDENCY_CHANGE.search(command):
        return "This command changes the project's dependencies, which needs the user's approval. Ask before adding, removing, or upgrading a package."
    if PROTECTED_IN_COMMAND.search(command) and WRITES_IN_COMMAND.search(command):
        return "This command appears to modify a file that defines a quality gate, which needs the user's approval. If the goal is a passing check, fix the code instead."
    return None


if __name__ == "__main__":
    raise SystemExit(main())
GUARDEOF

write_file tools/hooks/stop_gate.py <<'STOPEOF'
"""Stop hook: keep the agent working until the quality gates pass on its changes.

When the working tree has changed Python files (deletions included), this runs
what CI runs, in order: pre-commit on the files that still exist, the test suite
with branch coverage, and diff-cover at 100% of changed lines. The first failure
blocks the stop and hands its output back to the agent, so "done" means the
gates passed. When they pass, the user is shown the review brief
(``tools/review_brief.py``): where in the change to look.

A turn with no changed Python costs nothing: the gates are skipped.

To avoid an endless loop on a failure the agent cannot fix, a stop that is
already a retry (``stop_hook_active``) goes through, with a visible warning to
the user that the work is not verified.

Usage, from ``.claude/settings.json``, run from the project root with the hook
event JSON on stdin:
    uv run --no-sync python tools/hooks/stop_gate.py
Exit status is always 0; the decision is the JSON written to stdout.
"""

from __future__ import annotations

import html
import json
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TextIO

PYTHON_SUFFIXES: tuple[str, ...] = (".py", ".ipynb")
TESTS: tuple[str, ...] = ("uv", "run", "pytest", "-q", "--cov", "--cov-branch", "--cov-report=xml")
REVIEW_BRIEF: tuple[str, ...] = ("uv", "run", "--no-sync", "python", "-m", "tools.review_brief")
CHANGED_LINES: tuple[str, ...] = ("uv", "run", "diff-cover", "coverage.xml", "--compare-branch=main", "--include-untracked", "--fail-under=100")
COVERAGE_XML: Path = Path("coverage.xml")
# The gate tooling setup-standards.sh vendors. It is tested at 100% where it is
# maintained and kept byte-identical there, so a project's tests never import it;
# requiring a coverage record would fail every adoption. A project's own tools
# are not on this list and stay gated.
VENDORED_TOOLS: frozenset[str] = frozenset(
    {
        "tools/__init__.py",
        "tools/changes.py",
        "tools/check_coverage_records.py",
        "tools/check_declarations.py",
        "tools/check_suppressions.py",
        "tools/hooks/__init__.py",
        "tools/hooks/guard_protected.py",
        "tools/hooks/stop_gate.py",
        "tools/review_brief.py",
    }
)
# Each measured file's path, relative to the <source> directory that holds it: the
# project root for a bare --cov, or each root ``[tool.coverage.run] source`` names.
# Read by pattern: xml.etree would trip Ruff's S314 for no gain.
COVERAGE_FILENAME: re.Pattern[str] = re.compile(r'<class\b[^>]*\bfilename="([^"]*)"')
COVERAGE_SOURCE: re.Pattern[str] = re.compile(r"<source>([^<]*)</source>")
# Shared by every report of an unattributable record: the Stop hook, the CI check, and the review brief.
AMBIGUOUS_RECORD: str = (
    "Another coverage source holds a file at the same relative path, and Cobertura keeps one record per relative path "
    "(coveragepy/coveragepy#1508), so the record cannot be attributed to this module. "
    'Measure one common source instead, such as `source = ["."]` under `[tool.coverage.run]`.'
)
# Enough tail for the failing assertion or lint findings, without flooding the agent's context.
MAX_OUTPUT_CHARS: int = 6000


@dataclass(frozen=True)
class Result:
    """A finished command's exit status and its stdout and stderr combined."""

    returncode: int
    output: str


type Runner = Callable[[Sequence[str]], Result]


def run_command(command: Sequence[str]) -> Result:
    """Run a command from the current directory and capture everything it prints.

    Output is decoded as UTF-8, the encoding git uses for paths, rather than the
    locale's (cp1252 on Windows), which would garble non-ASCII file names.
    """
    completed: subprocess.CompletedProcess[str] = subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace", check=False)  # noqa: S603 -- argv comes from this module's fixed gate list, never a shell
    return Result(completed.returncode, completed.stdout + completed.stderr)


def read_coverage_xml(path: Path = COVERAGE_XML) -> str:
    """Return the coverage report's text, or "" when there is none, which records no file."""
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def main(stdin: TextIO = sys.stdin, stdout: TextIO = sys.stdout, run: Runner = run_command, read_coverage: Callable[[], str] = read_coverage_xml) -> int:
    """Read one Stop event, run the gates on changed Python, and block the stop on failure.

    Args:
        stdin: Source of the hook event JSON.
        stdout: Destination of the decision JSON; nothing is written to allow the stop.
        run: Executes one command; replaced by a fake in tests.
        read_coverage: Returns the coverage.xml text the test gate wrote; replaced in tests.

    Returns:
        Always 0, so Claude Code reads the decision from stdout.
    """
    event: dict[str, object] = json.loads(stdin.read())
    failure: tuple[str, Result] | None
    try:
        changes: ChangedPython = changed_python(run)
    except GitError as error:
        # Fail closed: a broken repository is not "nothing changed".
        failure = (" ".join(error.command), error.result)
    else:
        if not changes.existing and not changes.deleted:
            return 0
        failure = first_failure(changes.existing, run, read_coverage)
    if failure is None:
        show_review_brief(stdout, run)
        return 0
    label: str = failure[0]
    output: str = failure[1].output[-MAX_OUTPUT_CHARS:]
    decision: dict[str, object]
    if event.get("stop_hook_active"):
        decision = {"systemMessage": f"GATE FAILED: `{label}` still fails after a retry. Claude stopped anyway; this work is NOT verified."}
    else:
        decision = {
            "decision": "block",
            "reason": f"Quality gate failed: `{label}` (exit {failure[1].returncode}). Fix the cause, never by weakening configuration or adding a suppression, then finish.\n\n{output}",
        }
    stdout.write(json.dumps(decision))
    return 0


@dataclass(frozen=True)
class ChangedPython:
    """The working tree's changed Python files, split by whether they still exist."""

    existing: list[str]
    deleted: list[str]


def changed_python(run: Runner) -> ChangedPython:
    """Return the staged, unstaged, and untracked Python changes, each list sorted.

    A deletion is a change too: removing a module can break what imports it, so
    it triggers the tests even though there is no file left to lint.
    """
    candidates: set[str] = git_paths(("git", "ls-files", "-z", "--modified", "--others", "--exclude-standard"), run)
    candidates |= git_paths(("git", "diff", "-z", "--cached", "--name-only", "--relative", "--diff-filter=d"), run)
    deleted: set[str] = git_paths(("git", "ls-files", "-z", "--deleted"), run)
    deleted |= git_paths(("git", "diff", "-z", "--cached", "--name-only", "--relative", "--diff-filter=D"), run)
    return ChangedPython(
        existing=sorted(path for path in candidates - deleted if path.endswith(PYTHON_SUFFIXES)),
        deleted=sorted(path for path in deleted if path.endswith(PYTHON_SUFFIXES)),
    )


def show_review_brief(stdout: TextIO, run: Runner) -> None:
    """Show the user the review brief for the change that just passed the gates.

    The brief is information for the reviewer, never a gate: when it fails or says
    nothing, the stop goes through silently.
    """
    brief: Result = run(REVIEW_BRIEF)
    if brief.returncode == 0 and brief.output.strip():
        stdout.write(json.dumps({"systemMessage": brief.output.rstrip()}))


class GitError(Exception):
    """A git listing failed, so which files changed is unknown."""

    command: tuple[str, ...]
    result: Result

    def __init__(self, command: Sequence[str], result: Result) -> None:
        """Record the failing command and what git printed."""
        super().__init__(" ".join(command))
        self.command = tuple(command)
        self.result = result


def git_paths(command: Sequence[str], run: Runner) -> set[str]:
    """Return the paths a ``-z`` git listing prints.

    ``-z`` makes git print each path verbatim and NUL-terminated. Without it, git
    quotes any path with non-ASCII or special characters, and the quoted form
    would never match a Python suffix, so the gates would be skipped.

    Raises:
        GitError: git failed, for example outside a repository, on a broken
            configuration, or on a repository owned by another user.
    """
    result: Result = run(command)
    if result.returncode != 0:
        raise GitError(command, result)
    return {path for path in result.output.split("\0") if path}


def first_failure(files: list[str], run: Runner, read_coverage: Callable[[], str]) -> tuple[str, Result] | None:
    """Run each gate in order and return the first failure's label and result.

    pre-commit runs only when files remain to lint; given no files it would run
    nothing useful. Between the tests and diff-cover, every changed module must
    appear in the coverage report under a record attributable to it: a module no
    test imports is never recorded, and diff-cover silently skips files without a
    record.
    """
    failure: tuple[str, Result] | None
    if files:
        failure = run_gate(("uv", "run", "pre-commit", "run", "--files", *files), run)
        if failure is not None:
            return failure
    failure = run_gate(TESTS, run)
    if failure is not None:
        return failure
    missing: MissingRecords = unrecorded_modules(files, read_coverage(), Path.cwd())
    if missing.untested or missing.ambiguous:
        return "coverage record check", Result(1, record_check_output(missing))
    return run_gate(CHANGED_LINES, run)


def record_check_output(missing: MissingRecords) -> str:
    """Return the coverage record check's failure text: one section per kind of gap present."""
    sections: list[str] = []
    if missing.untested:
        listing: str = "\n".join(f"  {path}" for path in missing.untested)
        sections.append(f"No coverage record for:\n{listing}\nNo test imports these modules, so none of their lines are measured and diff-cover skips them. Add a test that exercises each one.")
    if missing.ambiguous:
        shared: str = "\n".join(f"  {path}" for path in missing.ambiguous)
        sections.append(f"Coverage record cannot be attributed for:\n{shared}\n{AMBIGUOUS_RECORD}")
    return "\n\n".join(sections)


def run_gate(command: Sequence[str], run: Runner) -> tuple[str, Result] | None:
    """Run one ``uv run <tool> ...`` gate and return its label and result when it fails.

    A failed gate whose tool uv cannot even start is not installed, which no code change
    fixes, so the label and output say so instead of naming the command. Any other
    failure, uv's own included (a malformed ``pyproject.toml``), keeps its diagnostic.
    """
    result: Result = run(command)
    if result.returncode == 0:
        return None
    tool: str = command[2]
    probe: Result = run(("uv", "run", "--no-sync", tool, "--version"))
    if probe.returncode == 0 or f"Failed to spawn: `{tool}`" not in probe.output:
        return " ".join(command), result
    advice: str = f"`{tool}` is not installed in the project environment, so this gate cannot run. Change no code: tell the user to add it with `uv add --dev {tool}`, or to re-run setup-standards.sh with -y --update."
    return f"{tool} (not installed)", Result(result.returncode, f"{result.output}\n\n{advice}")


@dataclass(frozen=True)
class MissingRecords:
    """The changed modules whose coverage the report does not show, by cause."""

    untested: list[str]
    """Under a measured source, but no record names them: no test imports them."""
    ambiguous: list[str]
    """Recorded under a name another source also holds as a file, so the record may be that file's."""


class Gap(Enum):
    """Why a measured module's coverage cannot be read from the report."""

    UNTESTED = "untested"
    AMBIGUOUS = "ambiguous"


def unrecorded_modules(files: list[str], report: str, root: Path) -> MissingRecords:
    """Return the changed ``.py`` files the coverage report has no attributable record of.

    Only a file under one of the report's ``<source>`` directories can have a record,
    named relative to that directory; one outside every source, such as a test when
    ``[tool.coverage.run] source`` names the packages, is unmeasured by configuration
    and needs none. A report naming no source, or no report, measures ``root``, so
    nothing is waved through.

    Cobertura keeps one record per relative path and does not say which source it
    belongs to (coveragepy/coveragepy#1508). So a record counts only against a source
    that holds the file, and a name another source also holds as a file cannot be
    attributed: the module is reported as ambiguous, never passed.

    Notebooks are exempt: pytest-cov never measures them. So is the vendored gate
    tooling (``VENDORED_TOOLS``), which no project test imports.

    Args:
        files: Changed paths, relative to ``root``.
        report: The Cobertura report's text.
        root: The project root, against which the paths and relative sources resolve.
    """
    # Path equality ignores case and separator spelling on Windows, as the filesystem does.
    sources: list[Path] = [(root / html.unescape(source)).resolve() for source in COVERAGE_SOURCE.findall(report)] or [root.resolve()]
    names: list[str] = [html.unescape(name) for name in COVERAGE_FILENAME.findall(report)]
    gaps: dict[str, Gap | None] = {path: _record_gap((root / path).resolve(), sources, names) for path in files if path.endswith(".py") and path not in VENDORED_TOOLS}
    return MissingRecords(
        untested=[path for path, gap in gaps.items() if gap is Gap.UNTESTED],
        ambiguous=[path for path, gap in gaps.items() if gap is Gap.AMBIGUOUS],
    )


def _record_gap(path: Path, sources: list[Path], names: list[str]) -> Gap | None:
    """Return why ``path``'s coverage cannot be read from the records, or None when it can or need not be.

    A record names ``path`` only relative to a source that holds it. When that name
    also resolves to an existing file under another source, the single record may be
    that file's, so the gap is ambiguous.
    """
    owners: list[Path] = [source for source in sources if path.is_relative_to(source)]
    if not owners:
        return None
    claimed: list[str] = [name for owner in owners for name in names if owner / name == path]
    if not claimed:
        return Gap.UNTESTED
    if any(source / name != path and (source / name).is_file() for source in sources for name in claimed):
        return Gap.AMBIGUOUS
    return None


if __name__ == "__main__":
    raise SystemExit(main())
STOPEOF

# --------------------------------------------------------------------------- #
# Install the staged templates. setup_files.py is kept byte-identical to
# skill/tools/ by tests/test_setup_script.py; it needs only the standard
# library, so it runs before the project environment exists. The digests are
# generated by skill/tools/template_history.py from this script's git history.
# --------------------------------------------------------------------------- #

cat >"$WORK/setup_files.py" <<'SETUPEOF'
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
``[dependency-groups]`` is not compared: development tools the project lacks are
listed, then added with ``uv add --dev`` under the same rules as an outdated file.
A tool the project already names keeps its version.

The module runs standalone in the target repository, so it uses the standard
library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Callable, Collection, Mapping, Sequence
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

UV_ADD_FAILED: int = 3
"""Exit status when every file was installed but ``uv add`` failed; the setup script carries on, then fails."""


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


def run_command(command: Sequence[str]) -> int:
    """Run a command, its output going straight to the terminal, and return its exit status.

    Prints so far are flushed first: piped, they are block-buffered and would land after the command's output.
    """
    sys.stdout.flush()
    return subprocess.run(command, check=False).returncode  # noqa: S603 -- argv is uv add --dev and the baseline's requirement strings, never a shell


def main(argv: list[str] | None = None, ask: Callable[[str], str] = input, run: Callable[[Sequence[str]], int] = run_command) -> int:
    """Install the staged templates into the current directory.

    Args:
        argv: Command-line arguments, defaulting to ``sys.argv[1:]``.
        ask: Prompts the user and returns the reply; raises ``EOFError`` without one.
        run: Runs a command and returns its exit status; replaced by a fake in tests.

    Returns:
        0, or ``UV_ADD_FAILED`` when ``uv add`` failed; any other failure raises.
    """
    parser: argparse.ArgumentParser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("stage", type=Path, help="directory holding the templates, laid out as in the repository")
    parser.add_argument("--hashes", type=Path, required=True, help="JSON digests of every earlier template version")
    parser.add_argument("--yes", action="store_true", help="never ask; replace only what --update or --force allows")
    parser.add_argument("--update", action="store_true", help="with --yes, replace unedited earlier versions and add the dev tools pyproject.toml lacks")
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
    added: bool = add_dev_tools(templates, assume_yes=args.yes, update=args.update or args.force, ask=ask, run=run)
    return 0 if added else UV_ADD_FAILED


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


def add_dev_tools(templates: Mapping[str, str], *, assume_yes: bool, update: bool, ask: Callable[[str], str], run: Callable[[Sequence[str]], int]) -> bool:
    """List the baseline's development tools that ``pyproject.toml`` does not install, and add them with ``uv add --dev``.

    They are added after asking, or unasked under ``assume_yes`` with ``update``. A tool the
    project already names keeps whatever version it pins. Runs after ``install``, so a
    staged ``pyproject.toml`` always exists by now.

    Returns:
        False when ``uv add`` ran and failed.
    """
    if PYPROJECT not in templates:
        return True
    missing: list[str] = missing_dev_tools(tomllib.loads(Path(PYPROJECT).read_text(encoding="utf-8")), tomllib.loads(templates[PYPROJECT]))
    if not missing:
        return True
    print(f"\n{PYPROJECT} [dependency-groups] dev lacks: {', '.join(missing)}")
    if not (update if assume_yes else confirm("Add them with 'uv add --dev'? [y/N] ", ask)):
        print("Not added: add them with 'uv add --dev', or re-run with -y --update.")
        return True
    if run(["uv", "add", "--dev", *missing]) != 0:
        print("\n'uv add' failed (above); add them by hand, or copy them from the baseline.")
        return False
    return True


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
SETUPEOF

cat >"$WORK/hashes.json" <<'HASHEOF'
{
 "files": {
  ".claude/settings.json": [
   "026ad39eaa4afea7ed33856301f4c537c51370785269c7e10da89ae68ad9da82",
   "beb8f051008d7259df447306cd8ea9869dbf19f35376080fd4bc7ed0de90d8a9"
  ],
  ".gitattributes": [
   "2abf4a37e4c86b07efe43284e7136af0d5f7dc37059c988751390565fa40dce6"
  ],
  ".github/workflows/ci.yml": [
   "062488952e347ab7076f705cd89a85635c8e5a858a64aae71b43dd179aea1fd5",
   "1b72d5ee3708b47ee2f712c77e1df9d275245df3818b133a294c10037a6f4189",
   "3c619d62a2f3c3ac5dd598d52c18b541ebe5eac8f6c7e47b536f303a6210b32a",
   "3d74634f38daf5e61b5dba5444b97088e5de351d227419732ad5f270a5a0aa04",
   "558d21d0cdc66dc41db7553bf80a553d3014f840dd718aaa5d2422aaa0779407",
   "ef7ddbb3b1623a416fbdf6c7ec1a8b7b6e285eee6ace5048a2533e7450c8fd64",
   "ff87d7a0ef4670a3a95db28c5a4144291df149a8d836de5989b7d101d93188ea"
  ],
  ".github/workflows/mutation.yml": [
   "0111fa893e4fdf60771a6b29e541669e3f5191ec49e49f059fc0c3a6c643f922",
   "9083970bdf2c798fd5710f8ad2d480bca6b783b5abb2e7bd1702a5192e591f52",
   "ab9e2e0e59a1269f37b56a1cd4466fc952f2796fed1777b20a6b0d75fce76a55",
   "b626fc6c38fb861793c397fcb36b9890760041fa4e8acc23e960b686b708df91",
   "e3c58bae28c4ec86fa078d0bf29307b22d2bcb4fe772ea1f8befc8eef1829b2b"
  ],
  ".gitignore": [
   "abd5c51f23b8e555fb48b5c4b28103b9a7fc7ecceacd9ff6cbb73e1ac814af21",
   "ae86437e83820ef43b73a98c62db83b1f2d50f16a2c394849077c4f13a06c1b7",
   "e279f237c76653d2c47cd778479cba58089ca7617d37dd8a1e0da421995f59ab"
  ],
  ".pre-commit-config.yaml": [
   "2aca5bf0725afe7b605a6d4b1bb08c4bccc0cfae03f1b2627849fc3b743301af",
   "362170faf216c61530367fce609afe2b09e3de598488ffd2be86c47e6d7d7f17",
   "3e92832f817e483c793dc743c6273b65dffb4d9f9e1fd0556ddaa9b96a39cd2e",
   "6ce604477f8c8928bd64d4eb517a88216729639f529440fa494ea2671dd8ceaf",
   "976fabbc8796ece39d01d477f8d7ad3023d85b14f6fc394a6a951911ed6d21cb",
   "a3ed82f2726dd10bd9a5ec360f824c2ac81e8c074d74d860aad4f07fb9b4be31",
   "b4c08952f1e2c7a61a06ffcaafe4bcf935e7b5163e432e3b5726757f609f3d9c",
   "c173562759098fbc74717df06805a98ddeb1bd8b8382f78f1e70c06d67be5bee",
   "c3133cfe1581b414de030c3215785f07ba1ed8e41450c297bb872cc9c083b098"
  ],
  "suppressions.toml": [
   "17647f5f57f7691cba0353e4b762ae6afca3420579756e5e24d8787928886b42",
   "1fba69e5a598ef5ce6fc1e00963adf6baea4d15597bb361d55bc3c37e438b8bd"
  ],
  "tests/.gitkeep": [
   "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
  ],
  "tools/__init__.py": [
   "f60c1b67d606c773fb41bd05f1a9d51e94933eb2b947d4d65bd9d674588558b9"
  ],
  "tools/changes.py": [
   "6924eeadf231fce1e701335f4173cbbd50f258df3a5763ea8b12e8b19ee75ce5"
  ],
  "tools/check_coverage_records.py": [
   "3746ef3d83f1b5a0d338cca4fa4aa561434189c22bb10366af691211a013614f",
   "399b37381fefff67020d80933cb46fae02d7e9782ce339b8cea94e73e4b16e2e",
   "3a7b677cc5520a404ace1ba8b0bb1520c7cc71346dd9bec3a07ecf1ec3a8f8f3",
   "e1d1a6a9b30d3eb169063c4ac6b9220c2a1af19cfa370d4f9d5fedff07550d62"
  ],
  "tools/check_declarations.py": [
   "27e8ad6f8cc9436f6e712c89b413b8a64d030e02e872eb317a2f8d67a624d56a",
   "572b11a72259a8afbb0ec99ce21ca9cded53444983949c261c3b1a52c8696e54",
   "67554527c78bf95e1573ca3c1752e28ccb4db7c80e88d74bd1456d9f65778759",
   "70642cbf1a03131d1edc69d1fcda8f08b80c8689b6122295667938b72b9d6334",
   "d0f1364a001d5616f52970d7a471ad2c2820e435a622b7a6b363edc73e6ed8f9",
   "f9e2699d313f57992183115235610815fefcb758fa07d452d96d81f0996165d3"
  ],
  "tools/check_suppressions.py": [
   "4de0ff76d121c6f8638f027e4fdc70958fd19274c8bb24801a91b972572f092e",
   "7dd40b8ae5a8367f4ec20bd17eb0048ea200d4cb786234b5dac9b68d0823cd5e",
   "7df224a2c43c344cafe165df0e922fbe4028d46299c3c554bfce13122df0e0f9",
   "ab58c10d44859946605794a15a368161349c1a0582719e69f483146c1fe50937"
  ],
  "tools/hooks/__init__.py": [
   "ab532d8cd9a0f7b2525c673116ba45f2368bd56166e65b1863541e090fd21b0b"
  ],
  "tools/hooks/guard_protected.py": [
   "1b95ad9da9902149d977cd00cd484a13fff9399edb7b694fb563ace7778d5e97",
   "4637d39b94a3106cb1fa11ebc1ca46fc586e95e77f8692c36bc1c820c8a0b27b",
   "510764062fdd6d258a56aa7f9e8ee3729f959ac480fb1bc97917d20c2939ded0",
   "6b92ef9bf25ad82304d6b2ed34243929077d3c85ce3d9cff6a2c6d0cc305ea32",
   "7231795635fee1ecd9ca7e1018cbe834891bc47d3ff6701c7e784e7fff98c429",
   "7a4370b125283c970250197c326b05cf9c75d4a8d412e46f5ee4d2fe4957f39b",
   "9065de3fb8a4f0e30792a358218946e2c34e468ea1aa138f3987cd3f52752785",
   "d3e624d7d678977a95888816f4995b28f7ed7e9fbce6eefad3a51741d055ab07",
   "f232e75c6f8ef6af4d73cc106eb935a2bdf3b596af991fecc45524b80a46b647",
   "f5effd54169dcf6e1ffc50918fb369f6d6429faedfe9a43001551ba8fe9f71d3"
  ],
  "tools/hooks/stop_gate.py": [
   "21285496811452232ada10368a7b28c856803042ff43002f5c6cc9069f724fc4",
   "2d93d88c916cde43beb50f0be64fc93a042aabfa26cbb9fb22962ec57e0f5c4a",
   "2f55b25b7d19dbaa2ffcfcd2d334f823a64fcf2dfaad15dd460b452ff532b6e4",
   "453f1efb6fdc7d2e1e7f9d701b071cea1e27c5497e772ba1a7bbdb3779b4399a",
   "7f8637a92bafd2f227627fb2102b1473f24b33058fcc2020f4883752ba9d23a5",
   "92083f4f7276073b4d7c0e4a51a08884fac811415ff820fb22cdd4f00152b23c",
   "f8c6728c028cc00802d402bece1c85226e3d1cf0ddd3acfe07d1a5d67e53b2de"
  ],
  "tools/mutation.sh": [
   "22a8457a0dff9d678e1a02c6c51de8918344f906538525ee067e185199f5d260",
   "ff0235affdaf6540d4ec96e914a78425bbca81459d9d524f218f16c72d8e6272"
  ],
  "tools/review_brief.py": [
   "25b531b14e210b67431e195cb3cc86b38b5ef9ed78644d45b0661598b434a0f5",
   "6be6b92d69cd8b65936ad1d8408adf120791bfb00ae528621b14852b693dd268",
   "e682ca2ca805b4f33c71f9da149f34a365792931a984b9ae87f9b8b1f5bf99c5"
  ]
 },
 "tables": {
  "tool.complexipy": [
   "c6db7bf6b5db161dd56d20d193dcd0f15115ce600a25d6e661a8cca6abde03d9"
  ],
  "tool.coverage": [
   "41646aba1abd145587e7bd27515b63383beea92738b13cd53d63172b492d86bb",
   "c5e905e7ea482969d79fbe31a641554ac3da81784c71dcfedbb4fa629af99c13"
  ],
  "tool.mutmut": [
   "af6936f45c3f692f6a4c7ef42f36b4ef9ed9eb942d734a1018a7d95ce32fec9d"
  ],
  "tool.mypy": [
   "550f975951d7b572df206b35f17d3265d017cfb6171d9e94abe44047e216f14d"
  ],
  "tool.pyright": [
   "25e808dd0457764542064753015a71138b743b632f809248cedbaf25da23dd98",
   "c4c70aef5b0902dd02d97e45f79e68ba145987466b8880d9ce8cf98a6c3f3bb7"
  ],
  "tool.pytest": [
   "353b7a7310645cf12de5c1eeaf01ad48209f1854bfc3809f2da49c9caeb4648b",
   "3b2d702b046c23c2874014041d2e7f1882241bdabfa6c90e820b5057bbe0b43f",
   "3d58d107b91675103ed8e9ec9c7cdee8f2dceb67980d5b1c7c5aaaed6647b2f8",
   "9e5a761663f177eb63664efe302ed7c54c272ffac4b4767b594dcfee2795625c"
  ],
  "tool.ruff": [
   "43a3897c1412271fea4b45314d3ca645070eee45958a81af5a222a7286df1b24",
   "4f22834aad03dd9a529c6c30e891ea705d658dc35e38b9a8ebb8642de6dec9bd"
  ]
 }
}
HASHEOF

# --------------------------------------------------------------------------- #
# Models: asked per coding host (or, with -y, defaulted where none are recorded
# yet) and stored in ~/.claude/CLAUDE.md and ~/.claude/settings.json, and in
# Copilot's copilot-instructions.md, every write confirmed first. setup_models.py is kept byte-identical to skill/tools/ by
# tests/test_setup_script.py and, like setup_files.py, needs only the
# standard library. It runs before any repository file is written.
# --------------------------------------------------------------------------- #

cat >"$WORK/setup_models.py" <<'MODELSEOF'
"""Ask which models the standards' workflow uses on each coding host, and record the answers in that host's home.

Two hosts are known: Claude Code (``~/.claude``) and Copilot (``~/.copilot``, or
``COPILOT_HOME`` when the environment sets it). Setup first asks which hosts to
configure, offering the hosts already configured, else those whose home directory
exists, else Claude Code; ``--yes`` takes that answer unasked.

Three choices per host: the coordinator model (the main session's default; it runs
the tests), the coding model (agents that write code), and the adversarial
code-review model, asked as a provider (Codex or Claude on Claude Code; Copilot or
none on Copilot) and then a model. Model names are free text; the suggestions are
only aliases or picker names.

The answers live in a block of the host's instruction file (``CLAUDE.md``,
``copilot-instructions.md``) between two marker comments, and every other byte of
that file is kept. On Claude Code the coordinator is also written to ``model`` in
``~/.claude/settings.json``, keeping its other keys; an existing ``model`` is
replaced only on an interactive re-run whose coordinator answer differs from the
stored one. Copilot gets no settings file: its model is picked in the picker or with
``--model``. Every write of every host is listed and confirmed once; ``--yes``
assumes the confirmation, writes each host's defaults (Claude Code: coordinator
``sonnet``, coding ``opus``, the alias for the latest Opus, review ``codex``
``gpt-5.4``; Copilot: ``Claude Sonnet 5.5``, ``Claude Opus 5.5``, review ``copilot``
``GPT-6 Astra``), and keeps an existing block untouched. The block ends with a coder
guard: one line telling the host not to open the other agents' instruction files.

With ``--modules``, each chosen host's skills directory (``skills`` in its folder)
gets the coding skill, and the review skill when the host reviews its own code
(provider ``claude`` on Claude Code, ``copilot`` on Copilot). A provider ``codex``
puts the review skill in ``~/.agents/skills`` instead, and the reviewer guard in a
review scope block of ``$CODEX_HOME/AGENTS.md`` (else ``~/.codex/AGENTS.md``), with
markers of its own. Setup marks each skill directory it installs with
``.managed-by`` and writes only a missing or marked directory; a link or an unmarked
directory is reported and left as it is, and a marked one no longer wanted is listed,
never removed. With ``--installer``, the setup script is copied to
``~/.local/share/python-code-standards/setup-standards.sh``. The summary ends with how
well each reviewer is kept from the coding skill and the overlaps that remain.

A host is refused, and the run exits 1, when its instruction file cannot be read,
its markers do not form exactly one closed block (a START without a later END, an
END before its START, or a repeated marker), or its settings file is not a JSON
object; nothing of that host is written, and the other hosts go ahead. A file to
write that resolves, through a symbolic link, outside the home directory needs its
own confirmation; ``--yes`` skips it and exits 1. Each file is written to a
temporary name beside it and then replaced, and a host whose write fails is
reported without stopping the others; the run then exits 1.

The setup script runs this module before the project environment exists, so it
uses the standard library only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, fields, replace
from enum import StrEnum
from pathlib import Path
from typing import Any, TextIO

START: str = "<!-- python-code-standards:models -->"
END: str = "<!-- /python-code-standards:models -->"

SUGGESTED: dict[str, tuple[str, ...]] = {"codex": ("gpt-5.4", "gpt-5.4-mini"), "claude": ("opus", "sonnet", "haiku")}
"""Model aliases offered for each Claude Code review provider; the first is that provider's default."""

PICKER: tuple[str, ...] = (
    "Claude Opus 5.5",
    "GPT-6 Astra",
    "Claude Sonnet 5.5",
    "MAI Code 2 Flash",
    "MAI Code 2",
    "GPT-6.1 Sol",
    "GPT-6 Luna",
    "Gemini 4 Carbon",
    "GPT-6.1 Terra",
    "Gemini 4 Hydrogen",
    "GPT-6.2 Astra",
    "GPT-6.2 Sol",
    "Claude Sonnet 5",
    "Claude Haiku 5.5",
    "GPT-6 Sol",
    "GPT-5.6 Sol",
    "GPT-5.6 Luna",
    "GPT-5.3-Codex",
    "MAI-Code-1.1-Flash",
    "Gemini 4 Argon",
    "Gemini 3.8 Flash",
    "Grok 4.7",
    "Grok 4.6",
)
"""The model names Copilot's picker shows, in its order."""


@dataclass(frozen=True)
class ModelChoices:
    """The models the workflow uses."""

    coordinator: str
    coding: str
    reviewer_provider: str
    reviewer_model: str


DEFAULTS: ModelChoices = ModelChoices(coordinator="sonnet", coding="opus", reviewer_provider="codex", reviewer_model=SUGGESTED["codex"][0])

LABELS: dict[str, str] = {
    "coordinator": "Coordinator model (main session default; runs the tests)",
    "coding": "Coding model (agents that write code)",
    "reviewer_provider": "Adversarial code-review provider",
    "reviewer_model": "Adversarial code-review model",
}
"""The line label of each field in the block, which is also how it is read back."""


@dataclass(frozen=True)
class Target:
    """A place setup writes to: its name in the summary, its folder in the home directory or where an environment variable moves it, and the note the summary adds once it is configured."""

    name: str
    home_dir: str
    home_env: str | None
    gate_note: str


@dataclass(frozen=True)
class Host(Target):
    """A coding host's facts: where its files live, how its block reads, and what it offers.

    ``suggestions`` maps each reviewer provider to the models offered for it, the first
    being that provider's default, and ``"models"`` to those offered for the coordinator
    and coding questions. ``settings_model_key`` is None for a host whose settings file
    setup never writes. ``guard`` is the coder guard, the block's last line, and
    ``own_reviewer`` the provider that reviews from the host's own skills directory.
    """

    instructions_name: str
    settings_model_key: str | None
    heading: str
    defaults: ModelChoices
    providers: tuple[str, ...]
    suggestions: Mapping[str, tuple[str, ...]]
    guard: str
    own_reviewer: str


@dataclass(frozen=True)
class ReviewTarget(Target):
    """A reviewer that writes no code: its instruction file holds only the reviewer guard, and the review skill goes to ``skills_dir`` in the home directory."""

    instructions_name: str
    override_name: str
    heading: str
    guard: str
    skills_dir: str


@dataclass(frozen=True)
class Markers:
    """The comment pair that delimits one kind of block setup keeps in an instruction file."""

    start: str
    end: str
    kind: str


MODELS: Markers = Markers(START, END, "models")
REVIEW: Markers = Markers("<!-- python-code-standards:review -->", "<!-- /python-code-standards:review -->", "review scope")
"""Distinct from ``MODELS``, so a file holding both blocks never merges one into the other."""

CODING_SKILL: str = "python-code-standards"
REVIEW_SKILL: str = "review-standards"
MANAGED_BY: str = ".managed-by"
MANAGED_TEXT: str = "python-code-standards setup\n"
"""The marker file of a skill directory setup installed; only such a directory, or a missing one, is written."""


CLAUDE_CODE: Host = Host(
    name="claude-code",
    home_dir=".claude",
    home_env=None,
    instructions_name="CLAUDE.md",
    settings_model_key="model",
    heading="## Models",
    defaults=DEFAULTS,
    providers=tuple(SUGGESTED),
    suggestions={"models": SUGGESTED["claude"], **SUGGESTED},
    gate_note="The repository's stop gate in `.claude/settings.json` runs the checks when a Claude Code session ends.",
    guard="Other agents' instruction files (`AGENTS.md`, `.github/copilot-instructions.md`) are not for you; do not open them unless a change touches them.",
    own_reviewer="claude",
)

COPILOT: Host = Host(
    name="copilot",
    home_dir=".copilot",
    home_env="COPILOT_HOME",
    instructions_name="copilot-instructions.md",
    settings_model_key=None,
    heading="## Models (Copilot)",
    defaults=ModelChoices(coordinator="Claude Sonnet 5.5", coding="Claude Opus 5.5", reviewer_provider="copilot", reviewer_model="GPT-6 Astra"),
    providers=("copilot", "none"),
    # The default reviewer leads its list, since the first suggestion is a provider's default.
    suggestions={"models": PICKER, "copilot": ("GPT-6 Astra", *(name for name in PICKER if name != "GPT-6 Astra")), "none": ("none",)},
    gate_note="\n".join(
        [
            "Configured, not verified.",
            "Stop gate configured for Claude Code only. Copilot's mapping of the repo's `.claude/settings.json` hooks is unverified"
            " and Copilot already reads that file. To check by hand run the gates in `docs/quality-gates.md`.",
            "Pick the model in the picker or with `--model`; setup writes no Copilot model setting.",
            "Check by hand, once per surface:",
            "- [ ] VS Code agent mode: open a session, ask which models it was told to use, confirm each hook fires.",
            "- [ ] Copilot CLI: open a session, ask which models it was told to use, confirm each hook fires.",
        ]
    ),
    guard="Other agents' instruction files (`CLAUDE.md`, `.claude/`, `AGENTS.md`) are not for you; do not open them unless a change touches them.",
    own_reviewer="copilot",
)

HOSTS: tuple[Host, ...] = (CLAUDE_CODE, COPILOT)
"""Every host setup can configure, in the order they are asked and reported."""

CODEX: ReviewTarget = ReviewTarget(
    name="codex",
    home_dir=".codex",
    home_env="CODEX_HOME",
    gate_note="Codex reviews with the `review-standards` skill; the guard narrows what it opens, it does not forbid it.",
    instructions_name="AGENTS.md",
    override_name="AGENTS.override.md",
    heading="## Review scope",
    guard="You are a reviewer. Do not load the `python-code-standards` or `design-spec` skills and do not open `CLAUDE.md`, `.github/copilot-instructions.md` or `.claude/`. Use the `review-standards` skill.",
    skills_dir=".agents/skills",
)
"""Planned whenever a chosen host's review provider is ``codex``, its name."""

INSTALLER: Target = Target(
    name="installer",
    home_dir=".local/share/python-code-standards",
    home_env=None,
    gate_note="An installed skill that is not a link into a clone runs setup from this copy.",
)
INSTALLER_NAME: str = "setup-standards.sh"

GUARANTEES: dict[str, str] = {
    "codex": "structural: the coding skill is in no directory Codex scans (~/.agents/skills, a repository's .agents/skills); the guard in AGENTS.md is advisory.",
    "claude": "advisory: review-standards shares ~/.claude/skills with the coding skill, so only the guard keeps the reviewer from it.",
    "copilot": "advisory: review-standards shares Copilot's skills directory with the coding skill, so only the guard keeps the reviewer from it.",
    "none": "no reviewer, so no review skill is installed.",
}
"""How well each review provider is kept from the coding skill (design section 6A): structurally only for Codex."""


@dataclass(frozen=True)
class InvalidBlock:
    """An instruction text whose markers do not form exactly one closed block, and what is wrong with them."""

    reason: str


@dataclass(frozen=True)
class Invalid:
    """A host or review target setup refuses to touch, because one of its files cannot be read or merged into."""

    host: Target
    path: Path
    reason: str


@dataclass(frozen=True)
class Settings:
    """A host's parsed settings file and the key that holds its default model."""

    path: Path
    key: str
    values: dict[str, Any]


@dataclass(frozen=True)
class HostFiles:
    """What planning read for one host: its folder, its instruction text and the block it records, and its settings."""

    host: Host
    folder: Path
    memory: str
    stored: ModelChoices | None
    settings: Settings | None
    notes: tuple[str, ...]

    @property
    def instructions(self) -> Path:
        """Return the host's instruction file."""
        return self.folder / self.host.instructions_name


@dataclass(frozen=True)
class Change:
    """A file in a host's home to write, with the part of it the user is shown; nothing but its path when ``shown`` is empty."""

    path: Path
    text: str
    shown: str


@dataclass(frozen=True)
class Plan:
    """One target's writes, the links it will not write through, what the summary should say about it, and, for a host, the models it records."""

    host: Target
    folder: Path
    changes: tuple[Change, ...]
    notes: tuple[str, ...] = ()
    skipped: tuple[Path, ...] = ()
    choices: ModelChoices | None = None


@dataclass(frozen=True)
class Module:
    """A skill setup installs: its directory name and the exact text of each file, keyed by its POSIX path inside."""

    name: str
    files: Mapping[str, str]


type Writes = tuple[tuple[Change, ...], tuple[str, ...]]
"""Changes to plan and notes for the summary."""


class Status(StrEnum):
    """What happened to a host, as the summary names it."""

    WRITTEN = "written"
    UNCHANGED = "nothing to change"
    DECLINED = "not written (declined)"
    INVALID = "skipped (invalid)"
    FAILED = "failed"
    DESELECTED = "still configured; delete the block to remove it"


@dataclass(frozen=True)
class Outcome:
    """A target's result: its status, the files written and skipped, notes, and whether the run must fail."""

    host: Target
    status: Status
    failed: bool = False
    written: tuple[Path, ...] = ()
    skipped: tuple[Path, ...] = ()
    notes: tuple[str, ...] = ()


def main(
    argv: list[str] | None = None,
    ask: Callable[[str], str] = input,
    home: Callable[[], Path] = Path.home,
    resolve: Callable[[Path], Path] = Path.resolve,
    environ: Mapping[str, str] = os.environ,
) -> int:
    """Ask for the hosts and their models, or take the defaults, and record them in each host's home.

    Args:
        argv: Command-line arguments, defaulting to ``sys.argv[1:]``.
        ask: Prompts the user and returns the reply; raises ``EOFError`` without one.
        home: Returns the home directory holding each host's folder.
        resolve: Returns where a path really leads, following symbolic links.
        environ: The environment, read for ``COPILOT_HOME`` and ``CODEX_HOME``.

    Returns:
        1 when a host or Codex's file was refused as invalid or failed to write, or
        when ``--yes`` skipped a file that links outside the home directory; otherwise 0.
    """
    parser: argparse.ArgumentParser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--yes", action="store_true", help="never ask; write the defaults only for hosts with no models recorded yet")
    parser.add_argument("--modules", type=Path, help="a folder holding one subfolder per skill to install")
    parser.add_argument("--installer", type=Path, help=f"the setup script to keep a copy of in ~/{INSTALLER.home_dir}")
    parser.add_argument("--repo", type=Path, help="the target repository's root, only read to check what Codex scans there; default: the current directory, as the setup script runs from it")
    args: argparse.Namespace = parser.parse_args(argv)

    root: Path = home()
    modules: dict[str, Module] = load_modules(args.modules)
    loaded: list[HostFiles | Invalid] = [load(host, root, environ) for host in HOSTS]
    default: tuple[Host, ...] = selected_hosts(configured_hosts(loaded), detected_hosts(root, environ))
    chosen: tuple[Host, ...] = default if args.yes else ask_hosts(default, ask)
    plans: list[Plan | Invalid] = [inside_home(plan_host(files, assume_yes=args.yes, ask=ask, modules=modules, resolve=resolve), root, resolve, assume_yes=args.yes, ask=ask) for files in loaded if files.host in chosen]
    report: list[str] = isolation(plans, root, args.repo or Path.cwd())
    shared: list[Plan | Invalid | None] = [plan_review_target(root, environ, plans, modules, resolve), plan_installer(args.installer, root)]
    plans.extend(inside_home(plan, root, resolve, assume_yes=args.yes, ask=ask) for plan in shared if plan is not None)
    outcomes: list[Outcome] = [*apply(plans, assume_yes=args.yes, ask=ask), *deselected(loaded, chosen)]
    print(summarize(outcomes, report))
    return 1 if any(outcome.failed for outcome in outcomes) else 0


def read(path: Path) -> str:
    """Return a file's exact text, line endings included, or "" when it does not exist."""
    return path.read_text(encoding="utf-8", newline="") if path.is_file() else ""


def holds(path: Path, text: str) -> bool:
    """Return whether the file ``path`` already holds exactly ``text``; an unreadable file does not."""
    try:
        return path.is_file() and path.read_bytes() == text.encode()
    except OSError:
        return False


def load_modules(folder: Path | None) -> dict[str, Module]:
    """Return each skill in ``folder``, one per subfolder, by name; none without a folder."""
    if folder is None:
        return {}
    return {skill.name: Module(skill.name, {path.relative_to(skill).as_posix(): read(path) for path in sorted(skill.rglob("*")) if path.is_file()}) for skill in sorted(folder.iterdir()) if skill.is_dir()}


def host_folder(host: Target, home: Path, environ: Mapping[str, str]) -> Path:
    """Return the folder holding the target's files: the one its environment variable names when set, else its folder in ``home``."""
    moved: str = environ.get(host.home_env, "") if host.home_env else ""
    return Path(moved) if moved else home / host.home_dir


def detected_hosts(home: Path, environ: Mapping[str, str]) -> tuple[Host, ...]:
    """Return the hosts whose home directory exists, in its usual place or where the environment moves it; no file is read."""
    return tuple(host for host in HOSTS if (home / host.home_dir).is_dir() or host_folder(host, home, environ).is_dir())


def configured_hosts(loaded: Iterable[HostFiles | Invalid]) -> tuple[Host, ...]:
    """Return the hosts whose instruction file holds exactly one closed block."""
    return tuple(files.host for files in loaded if isinstance(files, HostFiles) and files.stored is not None)


def selected_hosts(configured: tuple[Host, ...], detected: tuple[Host, ...]) -> tuple[Host, ...]:
    """Return the hosts to configure unasked: those configured, else those detected, else Claude Code."""
    return configured or detected or (CLAUDE_CODE,)


def ask_hosts(default: tuple[Host, ...], ask: Callable[[str], str]) -> tuple[Host, ...]:
    """Return the hosts the user names, asking again until every name is known; no names at all take ``default``."""
    names: str = ", ".join(host.name for host in HOSTS)
    while True:
        try:
            reply: str = ask(f"Hosts to configure ({names}) [{', '.join(host.name for host in default)}]: ")
        except EOFError:
            return default
        wanted: set[str] = {name for name in re.split(r"[\s,]+", reply.strip()) if name}
        unknown: list[str] = sorted(wanted - {host.name for host in HOSTS})
        if unknown:
            print(f"Unknown host {', '.join(unknown)}; answer one or more of {names}.")
        elif wanted:
            return tuple(host for host in HOSTS if host.name in wanted)
        else:
            return default


def load(host: Host, home: Path, environ: Mapping[str, str]) -> HostFiles | Invalid:
    """Read and parse every file setup may change for the host, or say which one it must not touch and why."""
    folder: Path = host_folder(host, home, environ)
    path: Path = folder / host.instructions_name
    try:
        memory: str = read(path)
    except (OSError, UnicodeDecodeError) as error:
        return Invalid(host, path, f"cannot be read ({error})")
    stored: ModelChoices | InvalidBlock | None = stored_choices(memory, host)
    if isinstance(stored, InvalidBlock):
        return Invalid(host, path, stored.reason)
    settings: Settings | Invalid | None = load_settings(host, folder)
    if isinstance(settings, Invalid):
        return settings
    usual: Path = home / host.home_dir / host.instructions_name
    # VS Code may not honour the variable (documented for Copilot CLI only), so a moved file is worth a warning.
    notes: tuple[str, ...] = () if path == usual else (f"{host.home_env} moves the file to {path}; {usual} is not written, and a surface that ignores {host.home_env}, such as VS Code, may read it instead.",)
    return HostFiles(host, folder, memory, stored, settings, notes)


def load_settings(host: Host, folder: Path) -> Settings | Invalid | None:
    """Return the host's parsed ``settings.json`` (empty when absent); None for a host whose settings setup never writes."""
    if host.settings_model_key is None:
        return None
    path: Path = folder / "settings.json"
    try:
        values: object = json.loads(read(path) or "{}")
    except (OSError, ValueError) as error:  # ValueError covers both invalid JSON and invalid UTF-8.
        return Invalid(host, path, f"cannot be parsed ({error})")
    if not isinstance(values, dict):
        return Invalid(host, path, "is not a JSON object")
    parsed: dict[str, Any] = values
    return Settings(path, host.settings_model_key, parsed)


def block_span(text: str, markers: Markers = MODELS) -> tuple[int, int] | InvalidBlock | None:
    """Return where the one closed block of the given markers starts and ends, markers included.

    Returns:
        None when the text holds neither marker; an ``InvalidBlock`` when its markers form
        anything but one start followed by one end, since merging into such a text could
        span, and replace, the user's own lines.
    """
    starts: int = text.count(markers.start)
    ends: int = text.count(markers.end)
    if starts > 1 or ends > 1:
        return InvalidBlock(f"{starts} start and {ends} end markers; it may hold one {markers.kind} block only")
    start: int = text.find(markers.start)
    end: int = text.find(markers.end)
    if start < 0 and end < 0:
        return None
    if start < 0:
        return InvalidBlock(f"{markers.end} has no {markers.start} before it")
    if end < 0:
        return InvalidBlock(f"{markers.start} has no {markers.end} after it")
    if end < start:
        return InvalidBlock(f"{markers.end} comes before {markers.start}")
    return (start, end + len(markers.end))


def render_block(choices: ModelChoices, host: Host = CLAUDE_CODE) -> str:
    """Return the host's models block, markers included, with no trailing newline; the host's coder guard is its last line."""
    lines: list[str] = [f"- {LABELS[field.name]}: `{getattr(choices, field.name)}`" for field in fields(choices)]
    return "\n".join([START, host.heading, "", *lines, "", host.guard, END])


def stored_choices(text: str, host: Host = CLAUDE_CODE) -> ModelChoices | InvalidBlock | None:
    """Return the choices an instruction text records, a missing line taking the host's default; None without a block, ``InvalidBlock`` for bad markers."""
    span: tuple[int, int] | InvalidBlock | None = block_span(text)
    if span is None or isinstance(span, InvalidBlock):
        return span
    block: str = text[span[0] : span[1]]
    found: dict[str, str] = {}
    name: str
    label: str
    for name, label in LABELS.items():
        match: re.Match[str] | None = re.search(rf"^- {re.escape(label)}: `([^`]*)`", block, re.MULTILINE)
        if match:
            found[name] = match.group(1)
    return replace(host.defaults, **found)


def merge_block(text: str, block: str, markers: Markers = MODELS) -> str:
    """Return the text with its block of the given markers replaced by ``block``, or with ``block`` appended when it has none.

    Raises:
        ValueError: The text's markers are invalid; ``load`` and ``review_scope`` refuse such a file before any merge, so this guards only against a new caller.
    """
    span: tuple[int, int] | InvalidBlock | None = block_span(text, markers)
    start: int
    end: int
    match span:
        case InvalidBlock():
            raise ValueError(span.reason)
        case (start, end):
            return text[:start] + block + text[end:]
        case _:  # no block yet
            if not text:
                return block + "\n"
            return text + ("\n" if text.endswith("\n") else "\n\n") + block + "\n"


def merge_model(settings: Mapping[str, Any], model: str, *, overwrite: bool, key: str = "model") -> dict[str, Any]:
    """Return the settings with ``model`` under ``key``, keeping an existing one unless ``overwrite``."""
    if key in settings and not overwrite:
        return dict(settings)
    return {**settings, key: model}


def ask_choices(defaults: ModelChoices, ask: Callable[[str], str], host: Host = CLAUDE_CODE) -> ModelChoices:
    """Ask each of the host's questions, offering ``defaults``; the review model's default follows a changed provider."""
    print(f"\nModels for {host.name}:")
    coordinator: str = answer("Coordinator model, the main session's default; it runs the tests", host.suggestions["models"], defaults.coordinator, ask)
    coding: str = answer("Coding model, for agents that write code", host.suggestions["models"], defaults.coding, ask)
    provider: str = ask_provider(defaults.reviewer_provider, ask, host)
    model_default: str = defaults.reviewer_model if provider == defaults.reviewer_provider else host.suggestions[provider][0]
    reviewer: str = answer(f"Adversarial code-review model ({provider})", host.suggestions[provider], model_default, ask)
    return ModelChoices(coordinator=coordinator, coding=coding, reviewer_provider=provider, reviewer_model=reviewer)


def answer(question: str, suggestions: tuple[str, ...], default: str, ask: Callable[[str], str]) -> str:
    """Return the user's reply, or ``default`` for an empty reply or none at all."""
    try:
        reply: str = ask(f"{question} (e.g. {', '.join(suggestions)}) [{default}]: ").strip()
    except EOFError:
        return default
    return reply or default


def ask_provider(default: str, ask: Callable[[str], str], host: Host) -> str:
    """Return the review provider, asking again until the reply names one the host offers."""
    while True:
        provider: str = answer("Adversarial code-review provider", host.providers, default, ask).lower()
        if provider in host.providers:
            return provider
        print(f"Answer {' or '.join(host.providers)}.")


def plan_host(files: HostFiles | Invalid, *, assume_yes: bool, ask: Callable[[str], str], modules: Mapping[str, Module], resolve: Callable[[Path], Path]) -> Plan | Invalid:
    """Return the host's writes: none for an invalid host; else a settings repair only under ``assume_yes`` with a recorded block, or those recording the answers, and its skills.

    ``assume_yes`` answers with the host's defaults; otherwise the questions are asked,
    offering the recorded answers.
    """
    if isinstance(files, Invalid):
        return files
    choices: ModelChoices
    plan: Plan
    if assume_yes and files.stored is not None:
        # The block stays as it is; only a settings file missing its model is filled in from it.
        choices = files.stored
        plan = pending_changes(files, choices, overwrite=False, keep_block=True)
    else:
        choices = files.host.defaults if assume_yes else ask_choices(files.stored or files.host.defaults, ask, files.host)
        # Only a re-run whose user picked another coordinator replaces a settings model.
        overwrite: bool = files.stored is not None and choices.coordinator != files.stored.coordinator
        plan = pending_changes(files, choices, overwrite=overwrite, keep_block=False)
    changes: tuple[Change, ...]
    notes: tuple[str, ...]
    changes, notes = host_skills(files.host, files.folder / "skills", choices, modules, resolve)
    return replace(plan, changes=(*plan.changes, *changes), notes=(*plan.notes, *notes))


def host_skills(host: Host, skills: Path, choices: ModelChoices, modules: Mapping[str, Module], resolve: Callable[[Path], Path]) -> Writes:
    """Return the writes installing the host's skills in ``skills``: the coding skill always, the review skill when the host reviews its own code, else a note on a copy no longer wanted."""
    coding: Writes = install(modules.get(CODING_SKILL), skills, resolve)
    review: Writes = install(modules.get(REVIEW_SKILL), skills, resolve) if choices.reviewer_provider == host.own_reviewer else ((), unwanted(skills / REVIEW_SKILL))
    return (*coding[0], *review[0]), (*coding[1], *review[1])


def install(module: Module | None, skills: Path, resolve: Callable[[Path], Path]) -> Writes:
    """Return the writes installing ``module`` as a directory in ``skills``, or why that directory is left as it is.

    Only a missing directory, or one holding ``.managed-by``, is written, and the marker is
    its first file, so an interrupted install is still setup's to finish. A directory that
    is a link, or that setup did not install, is reported and never changed. Files already
    up to date are left out; files the module no longer holds are left in place.
    """
    if module is None:
        return (), ()
    folder: Path = skills / module.name
    real: Path = resolve(folder)
    if real != resolve(skills) / module.name:
        return (), (f"{folder} is a link to {real}; not managed by setup; left as is.",)
    if folder.exists() and not (folder / MANAGED_BY).is_file():
        return (), (f"{folder} is not managed by setup; left as is.",)
    wanted: dict[str, str] = {MANAGED_BY: MANAGED_TEXT, **module.files}
    return tuple(Change(folder / name, text, "") for name, text in wanted.items() if not holds(folder / name, text)), ()


def unwanted(folder: Path) -> tuple[str, ...]:
    """Return a note when ``folder`` is a skill setup installed that no chosen host wants there any more; it is never removed."""
    return (f"{folder} was installed by setup and is no longer wanted; delete it to remove it.",) if (folder / MANAGED_BY).is_file() else ()


def plan_review_target(home: Path, environ: Mapping[str, str], plans: Iterable[Plan | Invalid], modules: Mapping[str, Module], resolve: Callable[[Path], Path]) -> Plan | Invalid | None:
    """Return Codex's writes when a chosen host reviews with it, Codex's name being that provider; otherwise None.

    The writes are the reviewer guard block in its instruction file and the review skill in
    its skills directory. An override file beside the instruction file, which the reviewer
    reads instead, is reported.
    """
    target: ReviewTarget = CODEX
    if not any(isinstance(plan, Plan) and plan.choices is not None and plan.choices.reviewer_provider == target.name for plan in plans):
        return None
    folder: Path = host_folder(target, home, environ)
    scope: tuple[Change, ...] | Invalid = review_scope(target, folder)
    if isinstance(scope, Invalid):
        return scope
    changes: tuple[Change, ...]
    notes: tuple[str, ...]
    changes, notes = install(modules.get(REVIEW_SKILL), home / target.skills_dir, resolve)
    override: Path = folder / target.override_name
    if override.exists():
        notes = (f"{override} exists, and Codex reads it instead of {folder / target.instructions_name}, so the review scope block will be ignored.", *notes)
    return Plan(target, folder, (*scope, *changes), notes)


def review_scope(target: ReviewTarget, folder: Path) -> tuple[Change, ...] | Invalid:
    """Return the write putting the reviewer guard block in the target's instruction file, none when it is already there, or why the file is refused."""
    path: Path = folder / target.instructions_name
    try:
        text: str = read(path)
    except (OSError, UnicodeDecodeError) as error:
        return Invalid(target, path, f"cannot be read ({error})")
    span: tuple[int, int] | InvalidBlock | None = block_span(text, REVIEW)
    if isinstance(span, InvalidBlock):
        return Invalid(target, path, span.reason)
    block: str = "\n".join([REVIEW.start, target.heading, "", target.guard, REVIEW.end])
    merged: str = merge_block(text, block, REVIEW)
    return () if merged == text else (Change(path, merged, block),)


def plan_installer(source: Path | None, home: Path) -> Plan | None:
    """Return the write keeping a copy of the setup script where an installed skill finds it; None when no script was named."""
    if source is None:
        return None
    folder: Path = home / INSTALLER.home_dir
    path: Path = folder / INSTALLER_NAME
    text: str = read(source)
    return Plan(INSTALLER, folder, () if holds(path, text) else (Change(path, text, ""),))


def isolation(plans: Iterable[Plan | Invalid], home: Path, repo: Path) -> list[str]:
    """Return how well each chosen host's reviewer is kept from the coding skill, then what design section 6A leaves overlapping for the chosen hosts.

    The Codex guarantee is checked rather than assumed: a coding skill already in a
    directory Codex scans, ``.agents/skills`` in the home directory or in the target
    repository ``repo``, breaks it. With no Codex reviewer, a review skill setup once put
    in the home one is listed, never removed.
    """
    providers: dict[str, str] = {plan.host.name: plan.choices.reviewer_provider for plan in plans if isinstance(plan, Plan) and plan.choices is not None}
    lines: list[str] = [f"{name}, reviewer {provider}: {GUARANTEES.get(provider, 'unknown provider, so no review skill is installed.')}" for name, provider in providers.items()]
    skills: Path = home / CODEX.skills_dir
    codex: bool = CODEX.name in providers.values()
    if not codex:
        lines.extend(unwanted(skills / REVIEW_SKILL))
    else:
        scanned: tuple[Path, ...] = (skills / CODING_SKILL, repo / CODEX.skills_dir / CODING_SKILL)
        lines.extend(f"not structural while {visible} exists: Codex scans that directory and setup does not manage it; remove it by hand." for visible in scanned if visible.is_symlink() or visible.exists())
    if codex and COPILOT.name in providers:
        lines.append("overlap: Copilot (CLI and VS Code) also scans ~/.agents/skills, so it sees review-standards.")
    if {CLAUDE_CODE.name, COPILOT.name} <= providers.keys():
        lines.append("overlap: VS Code's Copilot also reads ~/.claude/skills, so it sees the Claude Code copy of python-code-standards.")
    return lines


def pending_changes(files: HostFiles, choices: ModelChoices, *, overwrite: bool, keep_block: bool) -> Plan:
    """Return the plan recording ``choices``, leaving out a file it would not change and, with ``keep_block``, the instruction file."""
    changes: list[Change] = []
    notes: list[str] = list(files.notes)
    if keep_block:
        notes.append(f"Kept the models in {files.instructions}; re-run setup without -y to change them.")
    else:
        block: str = render_block(choices, files.host)
        merged: str = merge_block(files.memory, block)
        if merged != files.memory:
            changes.append(Change(files.instructions, merged, block))
    settings: Settings | None = files.settings
    if settings is not None:
        updated: dict[str, Any] = merge_model(settings.values, choices.coordinator, overwrite=overwrite, key=settings.key)
        if updated != settings.values:
            changes.append(Change(settings.path, json.dumps(updated, indent=2) + "\n", f'"{settings.key}": "{choices.coordinator}"'))
        elif settings.values[settings.key] != choices.coordinator:
            notes.append(f'{settings.path} keeps "{settings.key}": "{settings.values[settings.key]}"; edit it by hand to use {choices.coordinator}.')
    return Plan(files.host, files.folder, tuple(changes), tuple(notes), choices=choices)


def inside_home(plan: Plan | Invalid, home: Path, resolve: Callable[[Path], Path], *, assume_yes: bool, ask: Callable[[str], str]) -> Plan | Invalid:
    """Return the plan keeping each change whose path resolves inside ``home`` or a folder the environment named, and each through an outside link the user confirmed.

    A file linked out of the home directory, such as a ``CLAUDE.md`` kept in a repository,
    is never written unasked: ``assume_yes`` skips it, and otherwise it needs its own yes.
    A host folder moved out of ``home`` by its environment variable counts as inside; the
    usual folder does not, since it may itself be a link into a repository.
    """
    if isinstance(plan, Invalid):
        return plan
    boundary: Path = resolve(home)
    moved: bool = plan.folder != home / plan.host.home_dir
    boundaries: tuple[Path, ...] = (boundary, resolve(plan.folder)) if moved else (boundary,)
    allowed: list[Change] = []
    skipped: list[Path] = []
    change: Change
    for change in plan.changes:
        target: Path = resolve(change.path)
        if any(target.is_relative_to(inside) for inside in boundaries):
            allowed.append(change)
        elif assume_yes:
            print(f"\n{change.path} is a link to {target}, outside {boundary}; -y never writes through it. Skipped; re-run setup without -y to confirm it.", file=sys.stderr)
            skipped.append(change.path)
        elif confirmed(f"\n{change.path} is a link to {target}, outside {boundary}.\nWrite through the link to {target}? [y/N] ", ask):
            allowed.append(change)
        else:
            print(f"  skip     {change.path}")
            skipped.append(change.path)
    return replace(plan, changes=tuple(allowed), skipped=tuple(skipped))


def apply(plans: list[Plan | Invalid], *, assume_yes: bool, ask: Callable[[str], str]) -> list[Outcome]:
    """Show every host's changes, then write them host by host once confirmed; ``assume_yes`` confirms unasked.

    A host whose write fails is reported and the others are still written; hosts
    already written are not rolled back.
    """
    plan: Plan | Invalid
    change: Change
    for plan in plans:
        if isinstance(plan, Invalid):
            print(f"\n{plan.path}: {plan.reason}. Nothing written for {plan.host.name}; repair the file, then re-run setup.", file=sys.stderr)
            continue
        for change in plan.changes:
            print(f"\n  write    {change.path}\n{change.shown}" if change.shown else f"  write    {change.path}")
    waiting: bool = any(isinstance(plan, Plan) and plan.changes for plan in plans)
    if not waiting:
        print("\nModels: nothing to change.")
    write: bool = waiting and (assume_yes or confirmed("\nWrite the changes above? [y/N] ", ask))
    if waiting and not write:
        print("Not written; re-run setup to choose the models again.")
    return [settle(plan, write=write, assume_yes=assume_yes) for plan in plans]


def settle(plan: Plan | Invalid, *, write: bool, assume_yes: bool) -> Outcome:
    """Write one host's changes when ``write`` holds, and return what became of the host.

    A link skipped under ``assume_yes`` fails the run, since the user was never asked.
    """
    if isinstance(plan, Invalid):
        return Outcome(plan.host, Status.INVALID, failed=True, notes=(f"{plan.path}: {plan.reason}",))
    refused: bool = assume_yes and bool(plan.skipped)
    if not plan.changes:
        return Outcome(plan.host, Status.UNCHANGED, failed=refused, skipped=plan.skipped, notes=plan.notes)
    if not write:
        return Outcome(plan.host, Status.DECLINED, skipped=plan.skipped, notes=plan.notes)
    written: list[Path] = []
    change: Change
    for change in plan.changes:
        try:
            replace_file(change.path, change.text)
        except OSError as error:
            print(f"\n{change.path}: not written ({error}).", file=sys.stderr)
            return Outcome(plan.host, Status.FAILED, failed=True, written=tuple(written), skipped=plan.skipped, notes=(*plan.notes, f"{change.path}: {error}"))
        written.append(change.path)
    return Outcome(plan.host, Status.WRITTEN, failed=refused, written=tuple(written), skipped=plan.skipped, notes=plan.notes)


def replace_file(path: Path, text: str) -> None:
    """Write ``text`` to the file ``path`` leads to, through a temporary file beside it, so an interruption leaves the old file or the new one.

    The temporary file takes the old file's permission bits and is removed when the replace fails.
    """
    target: Path = path.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    handle: int
    temporary: str
    handle, temporary = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
    stream: TextIO
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as stream:
            stream.write(text)
        if target.is_file():
            shutil.copymode(target, temporary)
        Path(temporary).replace(target)
    finally:
        Path(temporary).unlink(missing_ok=True)


def deselected(loaded: Iterable[HostFiles | Invalid], chosen: tuple[Host, ...]) -> list[Outcome]:
    """Return an outcome for each configured host the user did not choose, whose block is left as it is."""
    return [Outcome(files.host, Status.DESELECTED, notes=(str(files.instructions),)) for files in loaded if isinstance(files, HostFiles) and files.stored is not None and files.host not in chosen]


def summarize(outcomes: list[Outcome], report: Sequence[str] = ()) -> str:
    """Return the per-target summary (status, files written and skipped, notes, and, once configured, its gate note), then the review isolation ``report``."""
    lines: list[str] = ["\nModels summary:"]
    outcome: Outcome
    for outcome in outcomes:
        lines.append(f"{outcome.host.name}: {outcome.status}")
        lines.extend(f"  wrote    {path}" for path in outcome.written)
        lines.extend(f"  skipped  {path} (link outside home)" for path in outcome.skipped)
        lines.extend(f"  {note}" for note in outcome.notes)
        if outcome.status in {Status.WRITTEN, Status.UNCHANGED}:
            lines.extend(f"  {line}" for line in outcome.host.gate_note.splitlines())
    if report:
        lines.append("Review isolation (instructions narrow what a model loads; they do not forbid it):")
        lines.extend(f"  {line}" for line in report)
    return "\n".join(lines)


def confirmed(question: str, ask: Callable[[str], str]) -> bool:
    """Return whether the user answered yes; no answer at all means no."""
    try:
        reply: str = ask(question)
    except EOFError:
        return False
    return reply.strip().lower() in {"y", "yes"}


if __name__ == "__main__":
    raise SystemExit(main())
MODELSEOF

# --------------------------------------------------------------------------- #
# Skills: setup_models.py installs them in each chosen host's home, marked with
# .managed-by. The coding skill (python-code-standards) is every file git tracks
# under skill/ except skill/__init__.py, which only lets this repo's tests import
# it; review-standards is the review skill. Files the templates above already
# embed are copied from where they were staged, and the rest are embedded here.
# tests/test_setup_script.py keeps every one byte-identical to its source.
# --------------------------------------------------------------------------- #

staged=""
module=""
while read -r staged module; do
    mkdir -p "$(dirname "$MODULES/$module")"
    cp "$WORK/$staged" "$MODULES/$module"
done <<'REUSED'
files/.pre-commit-config.yaml python-code-standards/assets/pre-commit-config.yaml
files/.gitattributes python-code-standards/assets/gitattributes
files/.github/workflows/ci.yml python-code-standards/assets/ci.yml
files/.github/workflows/mutation.yml python-code-standards/assets/mutation.yml
files/.claude/settings.json python-code-standards/assets/claude-settings.json
files/suppressions.toml python-code-standards/assets/suppressions.toml
files/tools/check_declarations.py python-code-standards/tools/check_declarations.py
files/tools/changes.py python-code-standards/tools/changes.py
files/tools/check_suppressions.py python-code-standards/tools/check_suppressions.py
files/tools/check_coverage_records.py python-code-standards/tools/check_coverage_records.py
files/tools/review_brief.py python-code-standards/tools/review_brief.py
files/tools/mutation.sh python-code-standards/tools/mutation.sh
files/tools/hooks/__init__.py python-code-standards/tools/hooks/__init__.py
files/tools/hooks/guard_protected.py python-code-standards/tools/hooks/guard_protected.py
files/tools/hooks/stop_gate.py python-code-standards/tools/hooks/stop_gate.py
setup_files.py python-code-standards/tools/setup_files.py
setup_models.py python-code-standards/tools/setup_models.py
REUSED

module_file python-code-standards/SKILL.md <<'MOD_SKILL'
---
name: python-code-standards
version: 4.4.0
description: Standards for writing, editing, and reviewing Python. Produces strictly typed, documented, localized changes verified by execution, Ruff, a type checker, and tests. Use whenever Python is written, modified, refactored, reviewed, or debugged — including small edits, scripts, notebooks, and tests — and whenever a project's Python tooling, dependencies, or configuration change.
---

# Python Code Standards

Strictly typed, documented Python, verified by execution. Competent Python is assumed; this file covers only what overrides a default or drifts under pressure.

## Precedence

Current request → repository configuration (`pyproject.toml`, `ruff.toml`, pyright, mypy, pytest, and coverage config) → this document → tool defaults.

Repository configuration or file style that contradicts this document: stop before editing, name the clash, ask whether to convert or match. Never edit configuration to make a check pass.

## Variable declaration

**Every variable is annotated before its first binding**, using a PEP 526 bare annotation ahead of the statement. Declaring converts Pyright's inference into a checked assertion, so element-type drift fails at the declaration instead of propagating.

| Binding form | Declaration |
| --- | --- |
| assignment, loop target, `with` target, unpacking | required |
| match capture, class-body alias (outside enum bodies), instance attribute | required |
| comprehension or generator target | exempt |
| `except ... as` name, walrus, import | exempt — the language cannot annotate these |
| enum member (plain assignment in an `Enum` subclass body) | exempt — the typing spec forbids annotating these |

```python
row: dict[str, object]
for row in rows:
    ...


class Ingest:
    total: int  # declared in the class body

    def __init__(self) -> None:
        self.total = 0
```

Prefer dataclasses and Pydantic models over plain classes for anything holding state — their fields *are* class-body annotations, so they satisfy the attribute rule by construction. A plain class is the right choice when construction logic is non-trivial or the class inherits from a non-dataclass base.

`check_declarations.py` enforces this across modules and notebook code cells, and its output is the specification. Use the repository's own `tools/check_declarations.py` when it has one, since that is the copy CI and pre-commit run; otherwise `${CLAUDE_SKILL_DIR}/tools/check_declarations.py`. An in-file base class's declarations cover its subclasses. An enum whose base is defined in another module needs that base listed by its import name in `enum-bases` under `[tool.check-declarations]` in `pyproject.toml`; the violation says so. `B007` fires on a declared target unused in the body — rename to `_name`, keeping the declaration.

## Scope

- Run Ruff on changed files only. Preview with `ruff format --diff`; narrow the scope if it would rewrite unrelated content.
- Do not add `pyproject.toml`, tests, a lockfile, or config the request did not ask for, even to make verification runnable. Run what the repository supports; report the rest as unrun.
- Report pre-existing defects; do not fix them. One exception: a security defect on a line the change already touches — fix it and say so.

## Agent hook portability

The language and workflow guidance here can be reused by any host that loads this skill, but
the setup script installs Claude Code hooks. Hook event names, input/output JSON, and failure
semantics belong to the selected agent host; do not treat a shared `SKILL.md` or hook filename
as proof of compatibility. Before adapting a hook, read that host's current reference and
test its actual event schema and response contract. This guard's Copilot support recognizes
the documented PascalCase provider input format; its Copilot and VS Code Local output shapes
differ.

## Environment

`uv` for everything, Python 3.13+ (`requires-python = ">=3.13"`, Ruff `target-version = "py313"`).

```bash
uv venv                  uv add <pkg>            uv sync
uv python pin 3.13       uv add --dev <pkg>      uv run <command>
```

Every tool runs through `uv run` so the verified environment is the project environment; `uvx` only for non-dependencies. Runtime deps in `[project] dependencies`, tooling in `[dependency-groups] dev`. Commit `uv.lock` for applications, not libraries.

## Formatting and documentation

Ruff is authoritative and the checked-in config is the specification — don't restate its rules in prose or review. Line length **220**.

Never auto-apply unsafe fixes: inspect with `ruff check --unsafe-fixes --diff`, check `ruff rule <CODE>`, apply only when the behavioral effect is understood and tested.

Google-style docstrings on every module, class, and non-trivial function in source (optional in tests, where the name carries the meaning), describing the contract rather than narrating the implementation. `Args:`/`Returns:`/`Raises:` only where they add what the name and annotations don't. Never document `self`/`cls` or repeat annotations in prose. Comments explain *why*, and are updated whenever the code they describe changes. No placeholder ellipses in copy-ready code.

## Design and testing

- **Design shape.** Architecture is designed from the domain outward, per the `design-spec` skill, and so is each unit: its domain states are types, and its functions map one state to the next. Sketching a unit top-down — the entry point, then the calls it needs — is a way to find those states, not the order to build it in. Every function owns a decision. Red flags, fixed before review: a function that only forwards its arguments, functions split by time order (load, then validate, then write) rather than by what each one knows, an interface about as complex as its implementation, and two functions that depend on the same detail. A type that names a domain state, or a function for one use case, is not an extra abstraction.
- **Test-driven development.** No production code without a failing test that demands it. Outer loop: one acceptance test per use case, through the composition root with in-memory adapters. Inner loop: red, one failing test against the unit's public API, watched failing for the expected reason; green, the least code that passes; refactor with the suite green, extracting helpers there. Then ascend: revisit each new helper's interface from its caller.
- **Unit tests.** Fakes replace only ports — I/O, clocks, randomness, the network — injected as protocols. In-process collaborators are real, and helpers are tested through the public API unless they hold independently complex logic.

`references/testing.md` has the mechanics.

## Verification

Changed files only, through `uv run`, using the project's commands where they differ.

```bash
# 1. Execute the changed code through the narrowest practical entry point.
# 2. Lint, format, declarations, and both type checkers (pre-commit is in the dev group):
uv run pre-commit run --files <files>
# Repository without pre-commit: run the tools individually.
uv run ruff check --fix <files> && uv run ruff format <files>
uv run python "${CLAUDE_SKILL_DIR}/tools/check_declarations.py" <files>
uv run python "${CLAUDE_SKILL_DIR}/tools/check_passthrough.py" <files>   # not in pre-commit; run it in both cases. `# passthrough: allow` on a def line skips a protocol-named forwarder and is a suppression needing approval
uv run pyright <files> && uv run mypy <files>
# 3. Tests and coverage:
uv run pytest <tests> -q
uv run pytest <tests> --cov=<module> --cov-report=term-missing --cov-report=xml --cov-branch
uv run diff-cover coverage.xml --compare-branch=main --fail-under=100
```

Coverage on changed code: **100% statement and 100% branch**, both reported. `diff-cover` measures exactly the changed lines, and CI runs it the same way; `fail_under` is only the whole-project floor. If missed, say what is uncovered; never lower the threshold.

**Never claim anything passed unless the command ran and its output was observed.** Editor diagnostics such as `mcp__ide__getDiagnostics` or `mcp__claude-vscode__getDiagnostics` are not verification (see `references/typing.md`). When commands cannot run, open the reply with `UNVERIFIED — nothing below was run.`, list the exact commands in order, and state which claims depend on them.

## Suppressions

`# noqa`, `# type: ignore`, `# pyright: ignore`, `# pragma: no cover`, per-file ignores, disabled diagnostics, coverage omissions, `fail_under` reductions, and warning filters all require explicit authorization. Attempt a real fix first. If a genuine tool limitation remains, explain the diagnostic, why code can't fix it, and the narrowest suppression — then wait. `PGH` rejects blanket directives, and `RUF100` flags ones that stopped applying.

Private-usage errors (Pyright `reportPrivateUsage`) may be suppressed only inside unit tests, per line with `# pyright: ignore[reportPrivateUsage]`, and there without asking. In any other code, never: call the public API or make the name public.

## References

- `references/setup.md` — setting up or configuring a repository to follow these standards
- `assets/conformance.py` — a module in house style that passes the whole toolchain; read it instead of asking how something should look
- `references/typing.md` — annotation decisions and checkers; always when a dependency ships no types
- `references/sql-duckdb.md` — Python constructs, executes, or embeds SQL
- `references/testing.md` — writing or changing tests
- `references/domains.md` — Pydantic, concurrency, packaging, dependency security
MOD_SKILL

module_file python-code-standards/assets/conformance.py <<'MOD_CONFORMANCE'
"""Example module demonstrating the house Python style.

Loads rows from DuckDB and summarizes them, exercising the declaration rule
against every syntactic form the standards care about.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

import duckdb

logger: logging.Logger = logging.getLogger(__name__)

SELECT_EVENTS: str = """
SELECT
    event_id
  , event_name
  , event_count
FROM events
WHERE event_name = ?
"""


class EventCounter:
    """Mutable accumulator, declared in the class body rather than in ``__init__``.

    A plain class is deliberate here: a dataclass would satisfy the attribute rule
    by construction, so this demonstrates the rule where it actually costs
    something.
    """

    total: int
    seen: set[str]

    def __init__(self) -> None:
        """Start empty."""
        self.total = 0
        self.seen = set()

    def add(self, name: str, count: int) -> None:
        """Record one event.

        Args:
            name: Event name.
            count: Occurrences to add.
        """
        self.total += count
        self.seen.add(name)


type Json = bool | int | float | str | list[Json] | dict[str, Json] | None


def classify(payload: Json) -> str:
    """Describe a payload using structural pattern matching.

    Match captures are bindings, so each is declared before the statement. A
    precise subject type is what lets strict Pyright type the captures: matched
    against ``object``, a sequence pattern captures ``Unknown``.

    Args:
        payload: A decoded JSON value.

    Returns:
        A short description of the payload's shape.
    """
    head: Json
    rest: list[Json]
    name: str
    other: Json
    match payload:
        case [head, *rest]:
            return f"sequence of {len(rest) + 1} starting with {head!r}"
        case {"name": str() as name}:
            return f"mapping for {name}"
        case other:
            return f"scalar {type(other).__name__}"


@dataclass(frozen=True)
class EventSummary:
    """Aggregated counts for a single named event."""

    name: str
    total: int


def summarize(conn: duckdb.DuckDBPyConnection, name: str) -> EventSummary:
    """Return the aggregate count for a named event.

    Args:
        conn: Open DuckDB connection.
        name: Event name to filter on, bound as a parameter.

    Returns:
        The aggregated summary for the requested event.
    """
    rows: list[tuple[int, str, int]] = conn.execute(SELECT_EVENTS, [name]).fetchall()

    total: int = 0
    row: tuple[int, str, int]
    for row in rows:
        total += row[2]

    logger.debug("summarized event=%s rows=%d", name, len(rows))
    return EventSummary(name=name, total=total)


def write_report(path: Path, summaries: dict[str, int]) -> None:
    """Write one summary per line to the given path.

    Args:
        path: Destination file.
        summaries: Mapping of event name to total count.
    """
    handle: TextIO
    with path.open("w", encoding="utf-8") as handle:
        key: str
        value: int
        for key, value in summaries.items():
            handle.write(f"{key}={value}\n")
MOD_CONFORMANCE

module_file python-code-standards/references/domains.md <<'MOD_DOMAINS'
# Conditional domains

Read the relevant section when the work touches it.

## Domain modeling and configuration

- The boundary between the two: Pydantic where input is untrusted or structurally variable and runtime validation earns its cost; dataclasses everywhere else. Reaching for Pydantic on internal types buys validation nobody needs and a dependency in the hot path.
- Prefer frozen dataclasses for validated values, `slots=True` where measurement justifies it, and mutable ones only where mutation is the type's explicit responsibility.
- Design types so invalid states are hard to construct: discriminated unions with `Literal` over one model of conditionally valid optional fields, `NewType` or a value object for identifiers sharing a runtime representation, `Protocol` where behavior matters more than inheritance.
- Read environment variables once at the composition root, parse into a typed settings object, validate at startup, inject it. No environment reads, settings construction, or process exit at import time.
- Require explicit values for credentials, signing keys, and production endpoints; defaults only for non-sensitive settings. Document every variable: required, type, default, sensitivity.
- Never embed credentials, tokens, or environment-specific paths. Verify TLS by default. `DTZ` requires timezone-aware datetimes; `T20` keeps `print` out of library code.

## Pydantic

Applies when the project already uses it, or runtime validation at a boundary justifies it.

- Use it at untrusted or structurally variable boundaries: API payloads, configuration, external files, messages, ORM conversion. Not as a replacement for dataclasses or internal types needing no validation.
- Keep boundary models separate from domain models when invariants, mutability, or lifecycle differ. Separate request, update, persistence, and response models rather than one permissive model reused across unrelated operations.
- Decide explicitly whether each boundary permits coercion; prefer strict where it could hide malformed input, precision loss, or identifier confusion. Test every supported coercion and every value that must be rejected.
- Prefer `Annotated` and `Field` constraints over validators; use validators only for normalization, cross-field invariants, or rules the schema can't express, and keep them free of I/O and hidden mutation.
- Treat serialization as an external contract. Secret-aware types don't guarantee exclusion from every path — exclude sensitive fields explicitly from responses, logs, error details, and debug output. Test aliases, strictness, defaults, discriminators, and custom serializers wherever they're part of the contract.
- Prefer `pydantic-settings` where Pydantic is already present. A major-version migration is a behavioral change, not a rename: test accepted input, rejected input, coercion, validator ordering, aliases, ORM conversion, and serialized output. Keep it localized unless a project-wide migration was requested.

## Concurrency and performance

Applies when async execution, threads, processes, or a measured performance requirement is in play.

- Introduce concurrency only when the workload justifies it, and reuse the repository's model. Converting sync to async, or async to threads, is never an incidental refactor.
- A function doesn't become async merely because it performs I/O. Threads are for blocking I/O that can't use the project's async interfaces; they don't speed up CPU-bound Python. Processes need serialization cost, startup overhead, and testability accounted for first. (`ASYNC` catches blocking calls inside async functions.)
- Bound concurrency explicitly — never fan out unbounded from untrusted or variable-sized input. Prefer structured concurrency so child tasks can't outlive their caller.
- Define whether an operation is fail-fast, best-effort, or partially successful. `return_exceptions=True` only where exceptions are deliberately typed, inspected, and reported. Preserve input-to-result correspondence when completion order differs from submission order.
- Apply timeouts where the maximum acceptable duration is known, and distinguish timeout from cancellation from underlying failure. Task groups, clients, streams, and executors close on success, error, timeout, *and* cancellation.
- Optimize only against a measured problem, recording workload, baseline, metric, and method. Keep correctness tests around optimized code and benchmarks isolated from them.

## Packaging and dependency security

- Follow the repository's existing build backend, layout, metadata, and release process. New reusable packages: prefer `src` layout so tests verify the installed package; keep `__all__` intentional and `__init__.py` free of expensive imports, config reads, and connections.
- Run the dependency vulnerability audit in CI or before release, and secret detection where the repository handles credentials, production data, publishing, or deployment. Audit CI changes touching those.
- `uv.lock` changes and automated dependency updates go through the same verification as any other change.
- Never suppress a confirmed vulnerable dependency, leaked secret, or unsafe workflow finding without authorization and a documented risk decision.
MOD_DOMAINS

module_file python-code-standards/references/setup.md <<'MOD_SETUP'
# Setting up a repository

Read when asked to set up, configure, or upgrade a repository to follow these standards, or to start a new project.

## The setup script

Use `setup-standards.sh` rather than copying templates by hand. It writes CI and hook configuration, installs a git hook, runs `git add -A`, records the [models](#choose-the-models) for each coding host in its home (`~/.claude/CLAUDE.md` and `~/.claude/settings.json`, `~/.copilot/copilot-instructions.md`, and `~/.codex/AGENTS.md` for a Codex reviewer; with `-y`, the defaults, and only where none are recorded), [installs the skills](#installed-skills) in those homes, and with `--update` adds missing dev tools with `uv add --dev`, so first tell the user exactly that and wait for approval; `-y` only skips the script's own prompt, which cannot be answered from a non-interactive shell. Then run it from the repository root, with the options for the task below.

When this skill is a link into a clone, the script sits next to `skill/` in the clone:

```bash
bash "${CLAUDE_SKILL_DIR}/../setup/setup-standards.sh" -y
```

Otherwise setup installed this skill and kept a copy of itself in `~/.local/share/python-code-standards/`:

```bash
bash ~/.local/share/python-code-standards/setup-standards.sh -y
```

## Set up a new repository

- Run `setup-standards.sh -y`.
- Every missing file is created. Existing files are never replaced, only [reported](#what-the-script-reports).

## Upgrade a repository set up earlier

- Run `setup-standards.sh -y --update`.
- Use it to pick up newer templates and tools, for example a fixed `tools/check_declarations.py`.
- Replaces only **outdated** files and `[tool.*]` tables. **Edited** ones are kept and listed.
- Adds the baseline's dev tools that `[dependency-groups] dev` lacks, with `uv add --dev`. A tool the project already names keeps its version. Without `--update`, `-y` only lists them.
- `pyproject.toml` is saved as `pyproject.toml.orig` before any table changes, because a comment added inside a table does not count as an edit.

## Replace files the user edited

- Run `setup-standards.sh -y --force`.
- Only when the user asks to discard their changes to these files.
- Replaces **outdated** and **edited** items. Each edited file is saved as `<file>.orig` first.

## Run it in a terminal

- No options: lists the outdated items and asks once before replacing them. Edited ones are kept. Then asks before adding missing dev tools.
- `--force`: also asks, separately, before replacing edited ones.
- Claude's shell cannot answer a prompt, so Claude always passes `-y`.

## Choose the models

Before installing, the script asks which coding hosts to configure, then three questions per host. Model names are free text; the suggested names are not checked.

| Host | Instruction file | Detected when |
| --- | --- | --- |
| `claude-code` | `~/.claude/CLAUDE.md`, plus `model` in `~/.claude/settings.json` | `~/.claude` exists |
| `copilot` | `$COPILOT_HOME/copilot-instructions.md` when `COPILOT_HOME` is set, else `~/.copilot/copilot-instructions.md`; no settings file | `COPILOT_HOME` names an existing directory, or `~/.copilot` exists |

The host question offers the hosts already configured (their file holds a models block), else the detected ones, else `claude-code`; `-y` takes that answer.

| Question | Used for | `-y` default, `claude-code` | `-y` default, `copilot` |
| --- | --- | --- | --- |
| Coordinator model | The main session's default; it runs the tests. | `sonnet` | `Claude Sonnet 5.5` |
| Coding model | Agents that write code. | `opus` (the alias for the latest Opus) | `Claude Opus 5.5` |
| Adversarial code-review provider, then its model | The adversarial code review. | `codex` (or `claude`), `gpt-5.4` | `copilot` (or `none`), `GPT-6 Astra` |

- The answers are stored in the host's instruction file, between `<!-- python-code-standards:models -->` and `<!-- /python-code-standards:models -->`, under `## Models` (`## Models (Copilot)` for Copilot). Everything else in the file is kept byte for byte; without a block, one is appended. A missing line in a block takes that host's default.
- On `claude-code` the coordinator is also written to `model` in `~/.claude/settings.json`, keeping its other keys. Copilot gets no model setting, because its key is unverified: pick the model in the picker or with `--model`; `picker` is an accepted answer.
- Every write of every host is shown, then confirmed once; `-y` assumes the confirmation. Each file is written to a temporary file beside it, then replaced. A host whose write fails is reported, the others are still written, and setup carries on, then fails at the end.
- A re-run without `-y` asks again, offering the stored answers as defaults. Choosing a new coordinator then replaces the `model` in `settings.json`; nothing else replaces an existing one.
- `-y` writes the defaults only for a host without a block, and keeps an existing block untouched. Before running with `-y`, tell the user these defaults; to choose others, they run the script in a terminal.
- A host that is not chosen keeps its block; the summary lists it as still configured. Delete the block to remove it.
- A host is refused when its markers do not form exactly one closed block (a start marker without a later end marker, an end marker before its start, or a repeated marker), its instruction file cannot be read, or its `settings.json` is not a JSON object: the file and the problem are reported, none of that host's files is written, the other hosts go ahead, and setup carries on, then fails at the end. Repair the file, then re-run.
- A file to write that is a symbolic link resolving outside the home directory (for example a `CLAUDE.md` kept in a repository) is shown with its target and needs its own confirmation; `-y` skips it, reports it, and setup carries on, then fails at the end. A `COPILOT_HOME` outside the home directory counts as inside.
- The summary reports Copilot as configured, not verified, with a checklist to run once per surface (VS Code agent mode, Copilot CLI): open a session, ask which models it was told to use, confirm each hook fires. The stop gate is configured for Claude Code only. When `COPILOT_HOME` moves the file, the summary warns that VS Code may read `~/.copilot` instead.
- `~` is the home directory Python's `Path.home()` returns, on Windows and in WSL alike; under WSL that is the Linux home, not the Windows one.
- Each block ends with a guard line telling that host not to open the other agents' instruction files unless a change touches them: `AGENTS.md` and `.github/copilot-instructions.md` for `claude-code`; `CLAUDE.md`, `.claude/` and `AGENTS.md` for `copilot`. A block written before the guard existed still reads back; `-y` keeps it as it is, so the guard arrives with the next run without `-y`.

## Installed skills

The script embeds two skills and installs them in the homes of the chosen hosts, as part of the same confirmed write:

| Skill | Goes to |
| --- | --- |
| `python-code-standards` (this skill) | `~/.claude/skills/` for `claude-code`; `$COPILOT_HOME/skills/`, else `~/.copilot/skills/`, for `copilot` |
| `review-standards` (what a reviewer checks; no coding how-to) | by the host's review provider: `codex` to `~/.agents/skills/`, `claude` to `~/.claude/skills/`, `copilot` to Copilot's skills directory, `none` nowhere |

- Each installed skill directory holds a `.managed-by` file. Setup writes only a missing directory or one holding that file, and only the files that differ. A directory without it, or one that is a link (such as a clone linked in by hand), is reported as not managed by setup and left as it is. A marked directory no host wants any more, after a provider change, is listed, never removed.
- A file inside a marked directory that is a link resolving outside the home directory follows the same rule as the instruction files: its own confirmation, and `-y` skips it and fails at the end.
- For a `codex` reviewer, Codex's `$CODEX_HOME/AGENTS.md` (else `~/.codex/AGENTS.md`) gets a `## Review scope` block between `<!-- python-code-standards:review -->` and `<!-- /python-code-standards:review -->`: "You are a reviewer. Do not load the `python-code-standards` or `design-spec` skills and do not open `CLAUDE.md`, `.github/copilot-instructions.md` or `.claude/`. Use the `review-standards` skill." Its markers differ from the models block's, the rest of the file is kept byte for byte, and bad markers refuse the file as for a host. When `AGENTS.override.md` exists beside it, the summary says the block will be ignored, because Codex reads that file instead.
- The script copies itself to `~/.local/share/python-code-standards/setup-standards.sh`, where this skill finds it when it is not a link into a clone.
- The summary ends with how well each reviewer is kept from this skill: structural for a `codex` reviewer, since this skill is in no directory Codex scans (it says so when something else put a copy in `~/.agents/skills` or in the repository's `.agents/skills`; setup only looks there, it never writes in the repository); advisory for `claude` and `copilot`, whose review skill shares a directory with this one. It then lists the overlaps that remain for the chosen hosts: Copilot also scans `~/.agents/skills`, and VS Code's Copilot also reads `~/.claude/skills`. Instructions narrow what a model loads; they do not forbid it.

## What the script reports

A missing file is created. An existing one is listed with one of three statuses; `pyproject.toml` is compared one `[tool.*]` table at a time, and its `[project]`, dependencies, and tables the baseline does not define are never touched, except that missing dev tools are added as described above.

| Status | Meaning |
| --- | --- |
| current | Identical to the template; nothing to do. |
| outdated | An earlier version of the script wrote it and nobody edited it since, so replacing it loses nothing. |
| edited | Differs from every version the script has written: the user changed it, or the script never wrote it. |

- Backups are never staged. Compare each `.orig` file with its file, then delete it.
- Merge kept edits, such as the `"hooks"` block of `.claude/settings.json`, by hand.

## The first check

After installing, the script checks the whole repository once. The check is read-only: Ruff in report mode, the declaration checker, Pyright, and MyPy run directly, never through pre-commit, so no hook from an existing config runs and problems in existing code are listed, not fixed. A tool the project's own `pyproject.toml` does not install is reported as not run, as is the pre-commit git hook without `pre-commit`; re-run with `-y --update` to add them. Fixing them is a separate change for the user to approve; `uv run pre-commit run --all-files` applies Ruff's fixes and formatting. The hook it installs does apply them, but only to files in each later commit. Tests and coverage are separate checks.

## Templates

`assets/` holds the templates the script embeds, for copying into a repository by hand: `pyproject-baseline.toml` (the baseline for a new project), `pre-commit-config.yaml`, `gitattributes`, and `ci.yml`.

An application commits `uv.lock`: run `uv lock` once and commit it before CI, since `assets/ci.yml` installs with `--locked`.
MOD_SETUP

module_file python-code-standards/references/sql-duckdb.md <<'MOD_SQL'
# SQL and DuckDB

Applies whenever Python constructs, executes, or embeds SQL.

- **Never interpolate values into SQL.** Bind them: `conn.execute(sql, [param])` or named parameters. Ruff `S608` flags f-string and `%` composition, and that flag is never suppressed.
- Identifiers cannot be bound. When a table or column name must be dynamic, validate it against an explicit allowlist before composition.
- Keep SQL in module-level constants or `.sql` files, not inline at call sites, so statements are reviewable and testable alone.
- A builder returns SQL and parameters; a separate function executes it. Query construction and business logic do not share a function.
- Format multi-line SQL with uppercase keywords, one clause per line, leading commas in select lists. The 220-character limit applies to the Python line, not to SQL readability.
- Prefer the relational API or a bound query for programmatic composition; reserve string SQL for static statements.

DuckDB specifics:

- It ships `py.typed`, so no stubs. Annotate `duckdb.DuckDBPyConnection` and `duckdb.DuckDBPyRelation`.
- Manage connections with a context manager or explicit `close()`; do not rely on interpreter shutdown.
- Convert result sets to `TypedDict`, dataclasses, or a DataFrame with declared dtypes at the boundary. Raw tuples do not enter business logic.
- Tests use `duckdb.connect(":memory:")` with fixture data. No test touches a shared or networked database.
MOD_SQL

module_file python-code-standards/references/testing.md <<'MOD_TESTING'
# Testing

Standard pytest practice is assumed. What follows is what shapes the outcome.

## Test-first, outside-in

1. **Types first.** Name the domain states the unit moves data through and declare each as a type (frozen dataclass, Pydantic model, or `Literal`-tagged record), so each function maps one state to the next. Parse input once, at the edge, into a type that carries its invariant.
2. **Outer loop.** Write one failing acceptance test per use case, through the composition root, with in-memory adapters (DuckDB `:memory:`, a fake HTTP client) behind the ports. It stays red until the use case works end to end.
3. **Red.** Write one failing test against the unit's public API and run it alone (`uv run pytest <test_file>::<test_name> -q`); confirm it fails for the expected reason — a missing function or a wrong result, not an import typo or a broken fixture.
4. **Green.** Write the least production code that passes.
5. **Refactor** with the suite green. Helpers are extracted here, each named for the decision it owns, and are tested through the public API; give one its own tests only when it holds independently complex logic. Commit the step if the repository's workflow asks for it.
6. **Ascend.** Look at each new helper from its caller: change an interface that no longer fits, and merge any function that only forwards its arguments (`check_passthrough.py` finds them). Repeat from step 3 until the acceptance test passes.

Ports — I/O, time, randomness, the network — arrive through parameters or constructor injection as protocols, so a test swaps them without patching; unit tests replace them with fakes and nothing else. In-process collaborators are real. The acceptance tests cover the real wiring.

## Coverage

100% statement and branch coverage on changed code is the floor, not the goal — it follows from test-first, since no line exists without a test that demanded it. A line no test can reach is unreachable: delete it rather than suppress it. `# pragma: no cover` still needs explicit authorization.

## Practice

- Cover every new code path and changed behavior: normal operation, meaningful boundaries, expected failures. For a bug fix, add a test that fails before and passes after — write it first and watch it fail for the expected reason.
- Test observable behavior, not internals, unless a private unit holds independently complex logic.
- For security, authorization, financial, destructive, and data-integrity behavior, cover every known outcome, denial path, and failure mode. A coverage percentage does not substitute for scenario coverage.
- Assert exception *contracts* — type plus any stable message, code, or attribute callers rely on — not incidental wording.
- Parametrize when one behavior must hold across several inputs, with readable case IDs. Use separate tests when the behaviors genuinely differ. (`PT` enforces the mechanics; this is the judgment call it can't make.)
- Prefer fakes, in-memory implementations, and injected protocols over deep mocking. When mocking, use `autospec=True`/`spec_set` so a test cannot rely on attributes the real dependency lacks, and patch where the code under test looks the symbol up.
- Keep fixtures narrow in scope and named for the state they provide; no catch-all fixture. Anything touching global state, env vars, working directory, or registries restores it via `yield` teardown.
- `skip`/`skipif`/`xfail` need a documented reason and a tracking reference. Never use them to hide a regression from the current change.
- Register every custom marker; `--strict-markers` makes an unregistered one fail.
- Reuse the repository's async plugin and loop mode; do not change either as an unrelated edit.
- Run the narrowest relevant test first, then the affected module, then whatever detects regressions in consumers. Add `pytest-xdist` only where the repository already supports it.
MOD_TESTING

module_file python-code-standards/references/typing.md <<'MOD_TYPING'
# Typing

Strict typing is a requirement. The part no tool checks is the variable declaration rule in `SKILL.md`. Checker configuration lives in `assets/pyproject-baseline.toml` (`[tool.pyright]`, `[tool.mypy]`).

## Annotations

- Annotate every public function, method, class attribute, and meaningful internal boundary, including `-> None`.
- Prefer precise domain types over `Any`: `TypeAlias`, `Protocol`, `TypedDict`, `Literal`, dataclasses, value objects.
- Narrow through explicit checks or pattern matching, not casts — a cast that hides an invalid assumption is a deferred bug. `TypeGuard`/`TypeIs` only for a reusable predicate that genuinely establishes the type.
- Add generic parameters only when input and output types have a relationship callers must preserve.

## Checkers

Pyright and MyPy on the command line are the gate. Both run against the changed scope; both must be clean.

```bash
uv run pyright <files>
uv run mypy <files>
```

The PyPI `pyright` package is a wrapper that fetches a Node runtime on first use, which fails in air-gapped CI — install it via npm there, or substitute `basedpyright`. Strict mode is also hostile to AST and metaprogramming code; `assets/pyproject-baseline.toml` relaxes unknown-type reporting for `tools/` in one declared place rather than scattering ignores.

Pylance and the IDE's diagnostics bridge (`mcp__ide__getDiagnostics` or `mcp__claude-vscode__getDiagnostics`) are not a gate: the bridge is read-only, often absent, and reports only files the editor has opened, so an empty result means "nothing analyzed" as often as "no errors". Pylance runs Pyright's engine, so `uv run pyright` gives the same diagnostics on demand.

Checker disagreement points at a real imprecision in the type model. Fix it with annotations, typed adapters, protocols, or stubs — not suppressions.

## Untyped dependencies

Stop at the first step that works. Do not skip to a suppression.

1. Check for a `py.typed` marker in the installed package — if present, nothing is needed.
2. `uv add --dev types-<package>` (typeshed).
3. Vendor-published `<package>-stubs`.
4. Write `stubs/<package>/__init__.pyi` covering only the symbols used; register via `stubPath` (Pyright) or `mypy_path` (MyPy); commit it.
5. Isolate the untyped surface behind a typed adapter or `Protocol` so the imprecision cannot spread.

Only after all five fail is a suppression a candidate, and it still needs authorization.
MOD_TYPING

module_file python-code-standards/tools/__init__.py <<'MOD_TOOLSINIT'
"""Bundled enforcement tools for the python-code-standards skill."""
MOD_TOOLSINIT

module_file python-code-standards/tools/check_passthrough.py <<'MOD_PASSTHROUGH'
"""Report functions that only forward their arguments.

A pass-through is a ``def`` or ``async def`` whose body, apart from a leading
docstring, is one statement: ``return <call>`` or a bare ``<call>``, awaited or
not. The call's arguments are exactly the function's own parameters, each passed once
and unchanged (positionally, by keyword, or as ``*args``/``**kwargs``), in any order,
leaving out ``self`` and ``cls``. The callee may be any expression. Functions decorated
``@overload`` or ``@abstractmethod`` are skipped, as is one whose ``def`` line carries a
``# passthrough: allow`` comment (for a name a protocol dictates, such as an
``ast.NodeVisitor`` method). ``check_suppressions.py`` treats that comment as a
suppression, so it needs the user's approval in ``suppressions.toml``.

Usage:
    uv run python skill/tools/check_passthrough.py src tests
Prints one ``path:line name`` per finding, for ``.py`` files only. Exit status is 1 when
any is found, or when a path does not exist or a file cannot be parsed.
"""

from __future__ import annotations

import argparse
import ast
import io
import re
import sys
import tokenize
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

_DECLARATION_DECORATORS: frozenset[str] = frozenset({"overload", "abstractmethod"})
"""Decorators marking a function whose body is not its implementation; such functions are never reported."""
_MARKER: re.Pattern[str] = re.compile(r"#\s*passthrough:\s*allow", re.IGNORECASE)
"""The approval comment; ``check_suppressions.DIRECTIVE`` must match every spelling this does."""


@dataclass(frozen=True)
class Finding:
    """A function that does nothing but forward its arguments."""

    path: Path
    line: int
    name: str

    def render(self) -> str:
        """Return a single-line, editor-navigable description."""
        return f"{self.path}:{self.line} {self.name}"


def find_passthroughs(path: Path, source: str) -> list[Finding]:
    """Return every pass-through in one module, in source order.

    Args:
        path: File path, used for reporting.
        source: Module source text.

    Returns:
        One finding per pass-through ``def`` or ``async def``, including methods and nested functions, unless its ``def`` line is marked.
    """
    tree: ast.Module = ast.parse(source)
    marked: set[int] = _marked_lines(source)
    findings: list[Finding] = [
        Finding(path, node.lineno, node.name)
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.lineno not in marked and not _is_declaration(node) and _forwards_exactly(node)
    ]
    return sorted(findings, key=lambda finding: finding.line)


def _marked_lines(source: str) -> set[int]:
    """Return the lines whose comment carries the approval marker; text inside a string is not a comment."""
    return {token.start[0] for token in tokenize.generate_tokens(io.StringIO(source).readline) if token.type == tokenize.COMMENT and _MARKER.search(token.string)}


def _is_declaration(function: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Whether the function is an ``@overload`` or ``@abstractmethod``, whose body exists only to be replaced or overridden."""
    return any(_last_name(decorator) in _DECLARATION_DECORATORS for decorator in function.decorator_list)


def _last_name(expression: ast.expr) -> str:
    """Return the final name of ``name`` or ``module.name``, or ``"?"`` for any other expression."""
    if isinstance(expression, ast.Attribute):
        return expression.attr
    return _name(expression)


def _forwards_exactly(function: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Whether a function's single call passes exactly its own parameters, each once and unchanged."""
    call: ast.Call | None = _forwarded_call(function)
    return call is not None and sorted(_passed(call)) == sorted(_received(function.args))


def _forwarded_call(function: ast.FunctionDef | ast.AsyncFunctionDef) -> ast.Call | None:
    """Return the call a function's single statement makes, or ``None`` when its body is anything else."""
    body: list[ast.stmt] = function.body
    if _is_docstring(body[0]):
        body = body[1:]
    if len(body) != 1:
        return None
    statement: ast.stmt = body[0]
    value: ast.expr | None = statement.value if isinstance(statement, (ast.Return, ast.Expr)) else None
    if isinstance(value, ast.Await):
        value = value.value
    return value if isinstance(value, ast.Call) else None


def _is_docstring(statement: ast.stmt) -> bool:
    """Whether a statement is a bare string literal."""
    return isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant) and isinstance(statement.value.value, str)


def _passed(call: ast.Call) -> list[tuple[str, str]]:
    """Return a call's arguments as ``(form, name)`` pairs; an argument that is not a bare name gets the name ``"?"``."""
    positional: list[tuple[str, str]] = [("*", _name(argument.value)) if isinstance(argument, ast.Starred) else ("", _name(argument)) for argument in call.args]
    keyed: list[tuple[str, str]] = [("" if keyword.arg else "**", _name(keyword.value)) for keyword in call.keywords]
    return positional + keyed


def _name(expression: ast.expr) -> str:
    """Return the name an expression is, or ``"?"`` for anything that is not a bare name."""
    return expression.id if isinstance(expression, ast.Name) else "?"


def _received(arguments: ast.arguments) -> list[tuple[str, str]]:
    """Return a function's parameters as ``(form, name)`` pairs, leaving out ``self`` and ``cls``."""
    plain: list[ast.arg] = [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs]
    received: list[tuple[str, str]] = [("", parameter.arg) for parameter in plain if parameter.arg not in {"self", "cls"}]
    if arguments.vararg:
        received.append(("*", arguments.vararg.arg))
    if arguments.kwarg:
        received.append(("**", arguments.kwarg.arg))
    return received


def iter_python_files(roots: list[Path]) -> Iterator[Path]:
    """Yield every ``.py`` file among the given files, and under the given directories in sorted order (a directory named ``*.py`` is not one)."""
    root: Path
    for root in roots:
        if root.is_file():
            if root.suffix == ".py":
                yield root
        else:
            yield from sorted(match for match in root.rglob("*.py") if match.is_file())


def read_source(path: Path) -> str:
    """Return a module's text decoded the way Python does: honouring a byte-order mark or an encoding declaration."""
    handle: TextIO
    with tokenize.open(path) as handle:
        return handle.read()


def main(argv: list[str] | None = None) -> int:
    """Run the checker over the given paths.

    Args:
        argv: Command-line arguments, defaulting to ``sys.argv[1:]``.

    Returns:
        1 when any pass-through is found, a path does not exist, or a file cannot be parsed, otherwise 0.
    """
    parser: argparse.ArgumentParser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    args: argparse.Namespace = parser.parse_args(argv)

    path: Path
    for path in args.paths:
        if not path.exists():
            print(f"{path}: no such file or directory", file=sys.stderr)
            return 1

    found: bool = False
    for path in iter_python_files(args.paths):
        try:
            findings: list[Finding] = find_passthroughs(path, read_source(path))
        except SyntaxError as exc:
            print(f"{path}:{exc.lineno}:{exc.offset}: could not parse: {exc.msg}", file=sys.stderr)
            return 1
        finding: Finding
        for finding in findings:
            print(finding.render())
            found = True
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
MOD_PASSTHROUGH

module_file python-code-standards/tools/template_history.py <<'MOD_HISTORY'
"""Record the digest of every template version the setup script has ever written.

``setup_files.py`` replaces an existing file without warning only when the file is,
byte for byte, a template an earlier setup script wrote, so nothing the project
changed is lost. This builds that list from every committed version of the setup
script, plus the working copy, and embeds it in the script's ``HASHEOF`` heredoc.
``pyproject.toml`` is recorded table by table, since projects always edit it.

Run it after changing any template; a test fails until the digests cover them.

Usage (from the directory holding ``pyproject.toml``):
    uv run python -m skill.tools.template_history
"""

from __future__ import annotations

import argparse
import json
import re
import tomllib
from collections.abc import Iterable, Iterator, Mapping
from itertools import takewhile
from pathlib import Path

from .hooks.stop_gate import GitError, Result, Runner, run_command
from .setup_files import PYPROJECT, digest, table_digest

SCRIPT: Path = Path("setup/setup-standards.sh")
WRITER: re.Pattern[str] = re.compile(r"^write_file (\S+) (?:<<'(\w+)'|</dev/null)$")
"""A line that writes one file, from a quoted heredoc or as an empty file."""

TOML_OPENER: str = "<<'TOML'"
"""The heredoc holding the baseline ``pyproject.toml``, written by its own ``sed`` line."""

DELIMITER: str = "HASHEOF"


def main(argv: list[str] | None = None, run: Runner = run_command, script: Path = SCRIPT) -> int:
    """Embed the digests of every template version in the setup script.

    Args:
        argv: Command-line arguments, defaulting to ``sys.argv[1:]``.
        run: Runs git.
        script: The setup script to read and update.

    Returns:
        0; a git failure raises ``GitError``.
    """
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args(argv)
    current: str = script.read_text(encoding="utf-8")
    updated: str = embed(current, known_digests([*script_versions(run, script.as_posix()), current], recorded=embedded(current)))
    if updated == current:
        print(f"{script} is up to date")
        return 0
    script.write_text(updated, encoding="utf-8", newline="")
    print(f"updated {script}")
    return 0


def script_versions(run: Runner, path: str) -> list[str]:
    """Return the text of every committed version of a file, newest first, following it across moves.

    Each version is read at the path the file had in that commit, so moving the
    script loses none of its history.

    Raises:
        GitError: git failed, so the history would be incomplete.
    """
    command: tuple[str, ...] = ("git", "log", "--follow", "--format=%H", "--name-only", "--", path)
    result: Result = run(command)
    if result.returncode != 0:
        raise GitError(command, result)
    # Each commit prints its hash, then the file's path then, relative to the repository root.
    fields: list[str] = result.output.split()
    versions: list[str] = []
    commit: str
    then: str
    for commit, then in zip(fields[::2], fields[1::2], strict=True):
        show: tuple[str, ...] = ("git", "show", f"{commit}:{then}")
        shown: Result = run(show)
        if shown.returncode != 0:
            raise GitError(show, shown)
        versions.append(shown.output)
    return versions


def known_digests(scripts: Iterable[str], recorded: Mapping[str, Mapping[str, list[str]]]) -> dict[str, dict[str, list[str]]]:
    """Return the recorded digests plus those of every file and ``[tool.*]`` table any of the scripts writes.

    Digests are only ever added: a shallow clone sees little history, and dropping
    what it cannot see would make unedited files from older versions look edited.
    """
    files: dict[str, set[str]] = {path: set(digests) for path, digests in recorded.get("files", {}).items()}
    tables: dict[str, set[str]] = {table: set(digests) for table, digests in recorded.get("tables", {}).items()}
    script: str
    for script in scripts:
        path: str
        text: str
        for path, text in templates(script).items():
            if path == PYPROJECT:
                name: str
                value: object
                for name, value in tomllib.loads(text).get("tool", {}).items():
                    tables.setdefault(f"tool.{name}", set()).add(table_digest(value))
            else:
                files.setdefault(path, set()).add(digest(text))
    return {"files": _sorted(files), "tables": _sorted(tables)}


def _sorted(digests: Mapping[str, set[str]]) -> dict[str, list[str]]:
    """Return the digests in a stable order, so regenerating changes nothing."""
    return {key: sorted(digests[key]) for key in sorted(digests)}


def templates(script: str) -> dict[str, str]:
    """Return the text of each file a setup script writes, keyed by its path in the repository."""
    found: dict[str, str] = {}
    lines: Iterator[str] = iter(script.splitlines(keepends=True))
    line: str
    for line in lines:
        # bash ignores trailing blanks on the command line, but not on the closing delimiter line.
        opener: tuple[str, str | None] | None = _opener(line.rstrip())
        if opener is None:
            continue
        path: str = opener[0]
        delimiter: str | None = opener[1]
        found[path] = "" if delimiter is None else _heredoc_body(lines, delimiter)
    return found


def _heredoc_body(lines: Iterator[str], delimiter: str) -> str:
    """Consume and return a heredoc's lines, up to and including its closing delimiter line."""
    return "".join(takewhile(lambda body: body.rstrip("\n") != delimiter, lines))


def _opener(line: str) -> tuple[str, str | None] | None:
    """Return the path and heredoc delimiter a line starts writing, or None for any other line."""
    if line.endswith(TOML_OPENER):
        return PYPROJECT, "TOML"
    match: re.Match[str] | None = WRITER.match(line)
    return (match.group(1), match.group(2)) if match else None


def embed(script: str, digests: Mapping[str, Mapping[str, list[str]]]) -> str:
    """Return the script with its ``HASHEOF`` heredoc holding the digests as JSON, in their given order."""
    start: int
    end: int
    start, end = _digest_span(script)
    return script[:start] + json.dumps(digests, indent=1) + "\n" + script[end:]


def embedded(script: str) -> dict[str, dict[str, list[str]]]:
    """Return the digests the script's ``HASHEOF`` heredoc holds."""
    start: int
    end: int
    start, end = _digest_span(script)
    digests: dict[str, dict[str, list[str]]] = json.loads(script[start:end])
    return digests


def _digest_span(script: str) -> tuple[int, int]:
    """Return where the ``HASHEOF`` heredoc's body starts and ends in the script."""
    opener: str = f"<<'{DELIMITER}'\n"
    start: int = script.index(opener) + len(opener)
    return start, script.index(f"\n{DELIMITER}\n", start - 1) + 1


if __name__ == "__main__":
    raise SystemExit(main())
MOD_HISTORY

module_file python-code-standards/tools/vendor_templates.py <<'MOD_VENDOR'
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

SCRIPT: Path = Path("setup/setup-standards.sh")

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
    "MODELSEOF": Path("skill/tools/setup_models.py"),
    "MOD_SKILL": Path("skill/SKILL.md"),
    "MOD_CONFORMANCE": Path("skill/assets/conformance.py"),
    "MOD_DOMAINS": Path("skill/references/domains.md"),
    "MOD_SETUP": Path("skill/references/setup.md"),
    "MOD_SQL": Path("skill/references/sql-duckdb.md"),
    "MOD_TESTING": Path("skill/references/testing.md"),
    "MOD_TYPING": Path("skill/references/typing.md"),
    "MOD_TOOLSINIT": Path("skill/tools/__init__.py"),
    "MOD_PASSTHROUGH": Path("skill/tools/check_passthrough.py"),
    "MOD_HISTORY": Path("skill/tools/template_history.py"),
    "MOD_VENDOR": Path("skill/tools/vendor_templates.py"),
    "MOD_REVIEW": Path("../review-standards/SKILL.md"),
}
"""The file each heredoc delimiter vendors, as ``tests/test_setup_script.py`` checks them.

The ``MOD_`` heredocs are files of the skills setup installs that no repository template
already embeds; the review skill lives beside this project, at the repository root.
"""


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
MOD_VENDOR

module_file review-standards/SKILL.md <<'MOD_REVIEW'
---
name: review-standards
description: Use when reviewing a code change adversarially. Defines what counts as a defect, the project invariants a reviewer checks, and how to read the computed review brief. Does not teach how to write code.
---

# Review standards

You review a change; you do not write it. Report only defects you can show.

## What counts as a defect

- A behaviour that is wrong for some input you can name: a failing case, not a feeling.
- Data loss, a security hole, or an unchecked boundary (user input, file paths, SQL, shell).
- Changed behaviour with no test that would fail without the change.
- A new failure path nothing catches, or a swallowed error.
- A comment, docstring or spec that now describes code that changed.

Skip anything Ruff, pyright, mypy or the repository's tests already report. Skip style and naming.

## Project invariants to check

These are claims to verify, not rules to apply to your own writing.

1. Every changed line is covered by a test that fails without it (statement and branch).
2. No new suppression (`noqa`, `type: ignore`, `pragma: no cover`, per-file ignore, lowered threshold, warning filter) without the change saying who approved it.
3. No change to CI, hooks, or build configuration that the change does not state a reason for.
4. No dependency added, removed or upgraded without a stated reason.
5. A bug fix includes a regression test for that bug.

## Reading the review brief

The brief is computed, not judged: change size, gate files touched, dependency changes, added suppressions, the most complex changed functions, changed modules no test imports, surviving mutants. Look first where it points. A brief of "none"s means nothing needs a closer look; it does not mean the change is correct.

## Reporting

For each finding: file and line, the input or state that breaks it, what happens, and the smallest fix direction. Reproduce before reporting; if you cannot reproduce, say so and do not report it as a defect. Rank by impact. If you find nothing, say so plainly.
MOD_REVIEW

printf 'Choosing models and installing skills...\n'
# Any non-zero status (refused markers or link, bad arguments, a crash): setup
# carries on, so the gates are still installed and checked, and fails at the end.
MODELS_RC=0
uv run --no-project --python 3.13 python "$WORK/setup_models.py" --modules "$MODULES" --installer "$INSTALLER" ${MODEL_FLAGS[@]+"${MODEL_FLAGS[@]}"} || MODELS_RC=$?

printf '\nInstalling files...\n'
# Status 3: every file is installed but "uv add" failed. Setup carries on, so the
# checks still run, and fails at the end; any other failure stops it here.
SETUP_RC=0
uv run --no-project --python 3.13 python "$WORK/setup_files.py" "$FILES" --hashes "$WORK/hashes.json" ${INSTALL_FLAGS[@]+"${INSTALL_FLAGS[@]}"} || SETUP_RC=$?
if [ "$SETUP_RC" -ne 0 ] && [ "$SETUP_RC" -ne 3 ]; then
    exit "$SETUP_RC"
fi

# --------------------------------------------------------------------------- #
# Bootstrap the environment
# --------------------------------------------------------------------------- #

if [ -e .python-version ]; then
    printf '\n  skip   .python-version (already pins %s)\n' "$(cat .python-version)"
else
    printf '\nPinning Python 3.13...\n'
    uv python pin 3.13
fi

printf '\nSyncing the environment...\n'
uv sync --all-groups

# Filled by the steps below, then reported at the end.
CHECK_RC=0
NOT_RUN=()

printf '\nInstalling the pre-commit git hook...\n'
if uv run --no-sync pre-commit --version >/dev/null 2>&1; then
    uv run pre-commit install
else
    NOT_RUN+=("pre-commit git hook")
fi

# The checks read the files git tracks, so stage first. This is the state you
# are about to commit anyway (see "Next" below). The .orig backups --force
# makes are left unstaged: they are the user's old copies, to compare and delete.
printf '\nStaging files so the checks can see them...\n'
git add -A -- . ':(exclude)*.orig' ':(exclude)*.orig.*'

# Read-only: each tool runs directly in report mode, never through pre-commit.
# A repository that already had a .pre-commit-config.yaml keeps it, and its
# hooks (ruff --fix, end-of-file-fixer, Black) would rewrite files if run.

check() {
    # check <label> <tool> <args...>: run a tool from the project environment,
    # or record it as not run when an existing pyproject.toml does not install it.
    local label=$1
    shift
    if ! uv run --no-sync "$1" --version >/dev/null 2>&1; then
        NOT_RUN+=("$label")
        return 0
    fi
    printf '\n-- %s\n' "$label"
    uv run --no-sync "$@" || CHECK_RC=1
}

PY_FILES=()
while IFS= read -r path; do
    PY_FILES+=("$path")
done < <(git ls-files -- '*.py')

printf '\nChecking all files (read-only)...\n'
check "ruff lint" ruff check --no-fix
check "ruff format" ruff format --check
if [ "${#PY_FILES[@]}" -gt 0 ]; then
    check "declarations" python tools/check_declarations.py "${PY_FILES[@]}"
    check "pyright" pyright "${PY_FILES[@]}"
    check "mypy" mypy "${PY_FILES[@]}"
fi

# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #

if [ "${#NOT_RUN[@]}" -gt 0 ]; then
    printf '\nNot run, because this project does not install them: %s\n' "${NOT_RUN[*]}"
    printf 'Re-run setup with -y --update to add them, or add them with "uv add --dev"\n'
    printf 'and re-run setup.\n'
    CHECK_RC=1
fi

if [ "$SETUP_RC" -eq 3 ]; then
    printf '\nThe missing dev tools were not added: "uv add" failed (see above).\n'
    CHECK_RC=1
fi

if [ "$MODELS_RC" -ne 0 ]; then
    printf '\nThe models step failed or was refused (see above); the models may not be fully recorded.\n'
    printf 'Fix the cause and re-run setup, or run it without -y to confirm a linked file.\n'
    CHECK_RC=1
fi

if [ "$CHECK_RC" -eq 0 ]; then
    printf '\nchecks: PASS\n'
else
    printf '\nchecks: FAILED or INCOMPLETE -- read the output above. The checks modified no file; setup may have written files above.\n'
    printf '"uv run pre-commit run --all-files" applies the Ruff fixes and formatting;\n'
    printf 'review its diff before committing.\n'
fi

printf '\nNext (files are already staged):\n'
printf '  git commit -m "Add python-code-standards toolchain"\n'
printf '  # uv.lock is committed for an application; delete it + switch ci.yml for a library\n'

exit "$CHECK_RC"
