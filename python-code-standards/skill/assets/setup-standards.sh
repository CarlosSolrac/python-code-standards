#!/usr/bin/env bash
#
# setup-standards.sh -- configure a repository to follow the python-code-standards.
#
# Run it from inside the target repository; it operates on the repo your current
# directory is in, not on wherever this file lives:
#
#   cd ~/src/my-repo
#   ~/.claude/skills/python-code-standards/assets/setup-standards.sh
#
#   -y, --yes    never ask (required when stdin is not a tty); replace only what
#                --update or --force allows
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

set -euo pipefail

# --------------------------------------------------------------------------- #
# Arguments
# --------------------------------------------------------------------------- #

ASSUME_YES=0
INSTALL_FLAGS=()
arg=""
for arg in "$@"; do
    case "$arg" in
        -y | --yes)
            ASSUME_YES=1
            INSTALL_FLAGS+=(--yes)
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

# --------------------------------------------------------------------------- #
# pyproject.toml -- baseline verbatim, with only [project] name substituted.
# A repo directory name with '|' in it would break the sed; rename by hand then.
# --------------------------------------------------------------------------- #

sed "s|^name = \"example-project\"\$|name = \"${PROJECT_NAME}\"|" >"$FILES/pyproject.toml" <<'TOML'
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
    "complexipy>=8,<9",           # cognitive complexity cap, see [tool.complexipy]
    "deptry>=0.25,<0.26",         # unused, missing, and transitive dependencies
    "diff-cover>=10,<11",        # CI: 100% coverage of changed lines
    "mutmut>=3.8,<4; sys_platform != 'win32'",  # needs os.fork; on Windows run it through WSL
    "mypy>=2.4,<3",
    "pip-audit>=2.10,<3",         # CI: dependencies with known vulnerabilities
    "pre-commit>=4,<5",
    "pyright>=1.1.400,<2",       # PyPI wrapper; downloads a Node runtime on first run
    "pytest>=9.0.3,<10",         # 9.0.3 fixes PYSEC-2026-1845
    "pytest-cov>=6,<8",
    "ruff>=0.16.10,<0.17",       # pinned: minor releases change which rules fire
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

# --------------------------------------------------------------------------- #
# .pre-commit-config.yaml
# --------------------------------------------------------------------------- #

write_file .pre-commit-config.yaml <<'YAML'
# Baseline hooks. `uv run pre-commit run --files <changed files>` is the whole
# verification loop except execution and coverage, which stay manual because
# they need the narrowest practical entry point chosen per change.
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.16.10
    hooks:
      - id: ruff
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

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0 # diff-cover compares against the base branch

      - name: Install uv
        uses: astral-sh/setup-uv@v5
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

    def visit_For(self, node: ast.For) -> None:
        """Check the loop target, then the body."""
        self.visit(node.iter)
        self._bind(node.target)
        self.visit_body(node.body)
        self.visit_body(node.orelse)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        """Async loops behave identically."""
        self.visit_For(node)  # type: ignore[arg-type]

    def visit_With(self, node: ast.With) -> None:
        """Check each ``as`` target, then the body."""
        item: ast.withitem
        for item in node.items:
            self.visit(item.context_expr)
            if item.optional_vars is not None:
                self._bind(item.optional_vars)
        self.visit_body(node.body)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        """Async context managers behave identically."""
        self.visit_With(node)  # type: ignore[arg-type]

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

    def visit_Lambda(self, node: ast.Lambda) -> None:
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
``flake8: noqa``, ``mypy:`` and ``pyright:`` settings, ``complexipy: ignore``),
unless ``suppressions.toml`` lists its file and code (for a setting, its whole
value):

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
# file noqa, mypy and pyright file comments, complexipy's ignore), which silence
# more than a line. coverage.py honors "no cover" and "no branch" pragmas, and
# mutmut skips lines marked "no mutate".
DIRECTIVE: re.Pattern[str] = re.compile(r"#\s*(ruff:\s*noqa|flake8:\s*noqa|noqa|type:\s*ignore|pyright:\s*ignore|pyright:|mypy:|complexipy:\s*ignore|pragma:?\s*no\s*(?:cover|branch|mutate))", re.IGNORECASE)
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
        if self.kind in {"pragma", "complexipy", "mypy", "pyright"}:
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
check the Stop hook runs locally (``unrecorded_modules``). Notebooks are exempt:
pytest-cov never measures them.

Usage, after the test step has written coverage.xml:
    uv run python -m tools.check_coverage_records --base origin/main
Exit status is 1 when a changed module has no record or git fails.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path

from .changes import base_commit, changed_files
from .hooks.stop_gate import COVERAGE_XML, GitError, Runner, read_coverage_xml, run_command, unrecorded_modules


def main(argv: list[str] | None = None, run: Runner = run_command, read_coverage: Callable[[Path], str] = read_coverage_xml) -> int:
    """Report every module changed since the merge base that coverage.xml does not record.

    Args:
        argv: Command-line arguments, defaulting to ``sys.argv[1:]``.
        run: Executes git; replaced by a fake in tests.
        read_coverage: Returns a coverage report's text; replaced in tests.

    Returns:
        1 when a changed module has no coverage record or git fails, otherwise 0.
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
    missing: list[str] = unrecorded_modules(files, read_coverage(args.coverage))
    path: str
    for path in missing:
        print(f"{path}: no coverage record. No test imports this module, so none of its lines are measured and diff-cover skips it. Add a test that exercises it.")
    return 1 if missing else 0


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
from .hooks.stop_gate import PYTHON_SUFFIXES, GitError, Result, Runner, git_paths, run_command, unrecorded_modules

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
    missing: list[str] = unrecorded_modules(sorted(sources), report)
    if not missing:
        return "## Coverage: every changed module has a coverage record"
    noun: str = "module" if len(missing) == 1 else "modules"
    return "\n".join([f"## Coverage: {len(missing)} changed {noun} without a coverage record", *(f"- `{path}`" for path in missing)])


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
# mutmut needs os.fork, so it runs on Linux and macOS. On Windows, run it in WSL:
#   wsl -e bash tools/mutation.sh
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

jobs:
  mutation:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true

      - name: Mutation testing
        run: bash tools/mutation.sh

      - name: Upload survivors
        if: always()
        uses: actions/upload-artifact@v4
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
FILE_TOOLS: frozenset[str] = frozenset({"Edit", "Write", "MultiEdit"})
SHELL_TOOLS: frozenset[str] = frozenset({"Bash", "PowerShell"})

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
        Always 0, so Claude Code reads the decision from stdout.
    """
    event: dict[str, object] = json.loads(stdin.read())
    tool_input: dict[str, object] = cast("dict[str, object]", event.get("tool_input", {}))
    reason: str | None = protected_reason(str(event.get("tool_name", "")), {key: str(value) for key, value in tool_input.items()})
    if reason is not None:
        decision: dict[str, object] = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask", "permissionDecisionReason": reason}}
        stdout.write(json.dumps(decision))
    return 0


def protected_reason(tool_name: str, tool_input: dict[str, str]) -> str | None:
    """Return why this tool call needs the user's approval, or None when it does not."""
    if tool_name in FILE_TOOLS:
        path: str = tool_input.get("file_path", "")
        if is_protected(path):
            return f"{path} defines a quality gate. Changing it can make a failing check pass without a fix, so the user must approve. If the goal is a passing check, fix the code instead."
        return None
    if tool_name in SHELL_TOOLS:
        return command_reason(tool_input.get("command", ""))
    return None


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
# Each measured file's path, relative to the project root because TESTS runs a bare
# --cov from there. Read by pattern: xml.etree would trip Ruff's S314 for no gain.
COVERAGE_FILENAME: re.Pattern[str] = re.compile(r'<class\b[^>]*\bfilename="([^"]*)"')
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
    appear in the coverage report: a module no test imports is never recorded,
    and diff-cover silently skips files without a record.
    """
    failure: tuple[str, Result] | None
    if files:
        failure = run_gate(("uv", "run", "pre-commit", "run", "--files", *files), run)
        if failure is not None:
            return failure
    failure = run_gate(TESTS, run)
    if failure is not None:
        return failure
    unrecorded: list[str] = unrecorded_modules(files, read_coverage())
    if unrecorded:
        listing: str = "\n".join(f"  {path}" for path in unrecorded)
        return "coverage record check", Result(1, f"No coverage record for:\n{listing}\nNo test imports these modules, so none of their lines are measured and diff-cover skips them. Add a test that exercises each one.")
    return run_gate(CHANGED_LINES, run)


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


def unrecorded_modules(files: list[str], report: str) -> list[str]:
    """Return the changed ``.py`` files the coverage report has no record of.

    Notebooks are exempt: pytest-cov never measures them. So is the vendored gate
    tooling (``VENDORED_TOOLS``), which no project test imports.
    """
    recorded: set[str] = {html.unescape(name) for name in COVERAGE_FILENAME.findall(report)}
    return [path for path in files if path.endswith(".py") and path not in recorded and path not in VENDORED_TOOLS]


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
   "beb8f051008d7259df447306cd8ea9869dbf19f35376080fd4bc7ed0de90d8a9"
  ],
  ".gitattributes": [
   "2abf4a37e4c86b07efe43284e7136af0d5f7dc37059c988751390565fa40dce6"
  ],
  ".github/workflows/ci.yml": [
   "3c619d62a2f3c3ac5dd598d52c18b541ebe5eac8f6c7e47b536f303a6210b32a",
   "3d74634f38daf5e61b5dba5444b97088e5de351d227419732ad5f270a5a0aa04",
   "ef7ddbb3b1623a416fbdf6c7ec1a8b7b6e285eee6ace5048a2533e7450c8fd64"
  ],
  ".github/workflows/mutation.yml": [
   "0111fa893e4fdf60771a6b29e541669e3f5191ec49e49f059fc0c3a6c643f922"
  ],
  ".gitignore": [
   "abd5c51f23b8e555fb48b5c4b28103b9a7fc7ecceacd9ff6cbb73e1ac814af21",
   "ae86437e83820ef43b73a98c62db83b1f2d50f16a2c394849077c4f13a06c1b7",
   "e279f237c76653d2c47cd778479cba58089ca7617d37dd8a1e0da421995f59ab"
  ],
  ".pre-commit-config.yaml": [
   "3e92832f817e483c793dc743c6273b65dffb4d9f9e1fd0556ddaa9b96a39cd2e",
   "b4c08952f1e2c7a61a06ffcaafe4bcf935e7b5163e432e3b5726757f609f3d9c",
   "c173562759098fbc74717df06805a98ddeb1bd8b8382f78f1e70c06d67be5bee",
   "c3133cfe1581b414de030c3215785f07ba1ed8e41450c297bb872cc9c083b098"
  ],
  "suppressions.toml": [
   "17647f5f57f7691cba0353e4b762ae6afca3420579756e5e24d8787928886b42"
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
   "3746ef3d83f1b5a0d338cca4fa4aa561434189c22bb10366af691211a013614f"
  ],
  "tools/check_declarations.py": [
   "27e8ad6f8cc9436f6e712c89b413b8a64d030e02e872eb317a2f8d67a624d56a",
   "67554527c78bf95e1573ca3c1752e28ccb4db7c80e88d74bd1456d9f65778759",
   "70642cbf1a03131d1edc69d1fcda8f08b80c8689b6122295667938b72b9d6334",
   "f9e2699d313f57992183115235610815fefcb758fa07d452d96d81f0996165d3"
  ],
  "tools/check_suppressions.py": [
   "7dd40b8ae5a8367f4ec20bd17eb0048ea200d4cb786234b5dac9b68d0823cd5e",
   "7df224a2c43c344cafe165df0e922fbe4028d46299c3c554bfce13122df0e0f9",
   "ab58c10d44859946605794a15a368161349c1a0582719e69f483146c1fe50937"
  ],
  "tools/hooks/__init__.py": [
   "ab532d8cd9a0f7b2525c673116ba45f2368bd56166e65b1863541e090fd21b0b"
  ],
  "tools/hooks/guard_protected.py": [
   "510764062fdd6d258a56aa7f9e8ee3729f959ac480fb1bc97917d20c2939ded0",
   "7a4370b125283c970250197c326b05cf9c75d4a8d412e46f5ee4d2fe4957f39b",
   "d3e624d7d678977a95888816f4995b28f7ed7e9fbce6eefad3a51741d055ab07",
   "f232e75c6f8ef6af4d73cc106eb935a2bdf3b596af991fecc45524b80a46b647",
   "f5effd54169dcf6e1ffc50918fb369f6d6429faedfe9a43001551ba8fe9f71d3"
  ],
  "tools/hooks/stop_gate.py": [
   "21285496811452232ada10368a7b28c856803042ff43002f5c6cc9069f724fc4",
   "2f55b25b7d19dbaa2ffcfcd2d334f823a64fcf2dfaad15dd460b452ff532b6e4",
   "92083f4f7276073b4d7c0e4a51a08884fac811415ff820fb22cdd4f00152b23c",
   "f8c6728c028cc00802d402bece1c85226e3d1cf0ddd3acfe07d1a5d67e53b2de"
  ],
  "tools/mutation.sh": [
   "ff0235affdaf6540d4ec96e914a78425bbca81459d9d524f218f16c72d8e6272"
  ],
  "tools/review_brief.py": [
   "25b531b14e210b67431e195cb3cc86b38b5ef9ed78644d45b0661598b434a0f5"
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

printf 'Installing files...\n'
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

if [ "$CHECK_RC" -eq 0 ]; then
    printf '\nchecks: PASS\n'
else
    printf '\nchecks: FAILED or INCOMPLETE -- read the output above. No file was modified.\n'
    printf '"uv run pre-commit run --all-files" applies the Ruff fixes and formatting;\n'
    printf 'review its diff before committing.\n'
fi

printf '\nNext (files are already staged):\n'
printf '  git commit -m "Add python-code-standards toolchain"\n'
printf '  # uv.lock is committed for an application; delete it + switch ci.yml for a library\n'

exit "$CHECK_RC"
