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
#   -y, --yes    skip the confirmation prompt (required when stdin is not a tty)
#   -h, --help   print this header
#
# Self-contained: every template below is embedded, so the script also works
# copied on its own to a host with no clone of the standards repo. The embedded
# tools/check_declarations.py is kept byte-identical to skill/tools/ by
# tests/test_setup_script.py.
#
# It creates (never overwrites) these files, then bootstraps the environment:
#   pyproject.toml              ruff / pyright / mypy / pytest / coverage config
#   .pre-commit-config.yaml     the lint + type verification loop
#   .gitattributes              eol=lf as a property of the repo
#   .gitignore                  Python caches and build output (only if absent)
#   .github/workflows/ci.yml    CI: pre-commit --all-files + pytest --cov + diff-cover
#   tools/check_declarations.py the "annotate before first binding" checker
#   tools/__init__.py           makes tools importable as a package
#   tools/hooks/                Claude Code hooks: ask before a gate changes; block
#                               "done" until the gates pass on changed files
#   .claude/settings.json       registers those hooks for this project
#   tests/.gitkeep              pytest testpaths root
#
# A file that already exists is left untouched and reported as skipped, so an
# existing pyproject.toml is yours to merge by hand.

set -euo pipefail

# --------------------------------------------------------------------------- #
# Arguments
# --------------------------------------------------------------------------- #

ASSUME_YES=0
arg=""
for arg in "$@"; do
    case "$arg" in
        -y | --yes) ASSUME_YES=1 ;;
        -h | --help)
            sed -n '2,40p' "$0" | sed 's/^# \{0,1\}//'
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
# File writers: create only when absent, consume the heredoc either way
# --------------------------------------------------------------------------- #

CREATED=()
SKIPPED=()

absent() {
    # Return 0 (and make the parent dir) when $1 should be written; 1 when it
    # already exists.
    if [ -e "$1" ]; then
        SKIPPED+=("$1")
        printf '  skip   %s (already exists)\n' "$1"
        return 1
    fi
    mkdir -p "$(dirname "$1")"
    return 0
}

write_file() {
    # Write stdin to $1 when absent; otherwise drain stdin and move on.
    if absent "$1"; then
        cat >"$1"
        CREATED+=("$1")
        printf '  create %s\n' "$1"
    else
        cat >/dev/null
    fi
}

# --------------------------------------------------------------------------- #
# pyproject.toml -- baseline verbatim, with only [project] name substituted.
# A repo directory name with '|' in it would break the sed; rename by hand then.
# --------------------------------------------------------------------------- #

if absent pyproject.toml; then
    sed "s|^name = \"example-project\"\$|name = \"${PROJECT_NAME}\"|" >pyproject.toml <<'TOML'
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
    "diff-cover>=10,<11",        # CI: 100% coverage of changed lines
    "mypy>=1.18,<2",
    "pre-commit>=4,<5",
    "pyright>=1.1.400,<2",       # PyPI wrapper; downloads a Node runtime on first run
    "pytest>=8,<9",
    "pytest-cov>=6,<8",
    "ruff>=0.14,<0.15",          # pinned: minor releases change which rules fire
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
]
ignore = []
fixable = ["ALL"]
unfixable = []

[tool.ruff.lint.per-file-ignores]
# pytest's assert-based style and test-only fixtures trip the bandit rules.
# pytest's assert-based style trips bandit; test names carry the meaning that
# a mandatory docstring would only restate, so docstrings in tests are optional.
"tests/**/*.py" = ["S101", "S105", "S106", "D100", "D103", "INP001"]
# A file named test_*.py is a test file wherever it sits. Without these two
# patterns the ignores above never match a test written beside its module.
"test_*.py" = ["S101", "S105", "S106", "D100", "D103", "INP001"]
"**/test_*.py" = ["S101", "S105", "S106", "D100", "D103", "INP001"]
"conftest.py" = ["S101", "D100", "INP001"]
# AST and metaprogramming code cannot satisfy strict unknown-type reporting.
# A CLI tool prints by design; that is the intentional-output carve-out.
"tools/**/*.py" = ["INP001", "T201"]

[tool.ruff.lint.pydocstyle]
# This already disables the conflicting D rules; do not add redundant D2xx ignores.
convention = "google"

[tool.ruff.lint.flake8-tidy-imports]
ban-relative-imports = "parents"

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
testpaths = ["tests"]
# No build system, so the project is never installed; tests import it from the root.
pythonpath = ["."]

[tool.coverage.run]
branch = true

[tool.coverage.report]
# Whole-project floor. A project adopting this with untested legacy code starts
# at its current coverage and only raises it; CI's diff-cover step holds changed
# lines at 100% either way.
fail_under = 100
show_missing = true
TOML
    CREATED+=("pyproject.toml")
    printf '  create %s\n' "pyproject.toml"
fi

# --------------------------------------------------------------------------- #
# .pre-commit-config.yaml
# --------------------------------------------------------------------------- #

write_file .pre-commit-config.yaml <<'YAML'
# Baseline hooks. `uv run pre-commit run --files <changed files>` is the whole
# verification loop except execution and coverage, which stay manual because
# they need the narrowest practical entry point chosen per change.
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.14.0
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

      - name: Coverage of changed lines
        run: uv run diff-cover coverage.xml --compare-branch=origin/${{ github.base_ref || 'main' }} --fail-under=100
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
class definitions, and function parameters (annotated in the signature).

Usage:
    uv run python -m tools.check_declarations src tests
Exit status is 1 when any violation is found.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Violation:
    """A name bound in a scope before it was annotated."""

    path: Path
    line: int
    column: int
    name: str

    def render(self) -> str:
        """Return a single-line, editor-navigable description."""
        return f"{self.path}:{self.line}:{self.column}: {self.name} bound before annotation"


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

    def __init__(self, path: Path, declared: set[str]) -> None:
        """Initialize the checker.

        Args:
            path: File being checked, used for reporting.
            declared: Names already annotated or otherwise exempt in this scope.
        """
        self.path: Path = path
        self.declared: set[str] = set(declared)
        self.violations: list[Violation] = []
        self.class_attributes: dict[str, set[str]] = {}

    def _bind(self, node: ast.expr) -> None:
        """Record a binding target, reporting it when it lacks a prior annotation."""
        if isinstance(node, ast.Name):
            if node.id not in self.declared and not node.id.startswith("__"):
                self.violations.append(Violation(self.path, node.lineno, node.col_offset, node.id))
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
        """Check every assignment target."""
        self.visit(node.value)
        target: ast.expr
        for target in node.targets:
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
        bindings and can be pre-declared, so the rule applies to them.
        """
        if isinstance(node, ast.MatchAs):
            if node.pattern is not None:
                self._bind_pattern(node.pattern)
            if node.name is not None:
                self._bind(ast.Name(id=node.name, lineno=node.lineno, col_offset=node.col_offset))
            return
        if isinstance(node, ast.MatchStar):
            if node.name is not None:
                self._bind(ast.Name(id=node.name, lineno=node.lineno, col_offset=node.col_offset))
            return
        if isinstance(node, ast.MatchMapping):
            sub: ast.pattern
            for sub in node.patterns:
                self._bind_pattern(sub)
            if node.rest is not None:
                # ``**rest`` has no AST node of its own; report it at the end of
                # the mapping so it sorts after the keys it follows in source.
                self._bind(ast.Name(id=node.rest, lineno=node.end_lineno or node.lineno, col_offset=node.end_col_offset or node.col_offset))
            return
        if isinstance(node, (ast.MatchSequence, ast.MatchOr)):
            element: ast.pattern
            for element in node.patterns:
                self._bind_pattern(element)
            return
        if isinstance(node, ast.MatchClass):
            positional: ast.pattern
            for positional in [*node.patterns, *node.kwd_patterns]:
                self._bind_pattern(positional)

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
        """Exempt comprehension targets, which occupy their own scope."""
        generator: ast.comprehension
        for generator in generators:
            self.visit(generator.iter)
            target: ast.AST
            for target in ast.walk(generator.target):
                if isinstance(target, ast.Name):
                    self.declared.add(target.id)

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
        """Imports bind names that cannot be annotated."""
        alias: ast.alias
        for alias in node.names:
            self.declared.add((alias.asname or alias.name).split(".")[0])

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Same treatment as plain imports."""
        alias: ast.alias
        for alias in node.names:
            self.declared.add(alias.asname or alias.name)

    def visit_Global(self, node: ast.Global) -> None:
        """Names declared global are managed in the module scope."""
        self.declared.update(node.names)

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        """Names declared nonlocal are managed in an enclosing scope."""
        self.declared.update(node.names)

    def _enter_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda) -> None:
        """Recurse into a function body with its parameters pre-declared."""
        parameters: set[str] = set()
        arg: ast.arg
        for arg in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]:
            parameters.add(arg.arg)
        if node.args.vararg is not None:
            parameters.add(node.args.vararg.arg)
        if node.args.kwarg is not None:
            parameters.add(node.args.kwarg.arg)

        inner: ScopeChecker = ScopeChecker(self.path, self.declared | parameters)
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

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """A class binds its own name, opens a scope, and declares its attributes."""
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

        inner: ScopeChecker = ScopeChecker(self.path, self.declared)
        inner.class_attributes = self.class_attributes
        inner.visit_body(node.body)
        self.violations.extend(inner.violations)

    def visit_body(self, body: list[ast.stmt]) -> None:
        """Visit statements in source order so declarations precede bindings."""
        statement: ast.stmt
        for statement in body:
            self.visit(statement)


def check_source(path: Path, source: str) -> list[Violation]:
    """Return every declaration violation in one module.

    Args:
        path: File path, used for reporting.
        source: Module source text.

    Returns:
        Violations in source order.
    """
    tree: ast.Module = ast.parse(source, filename=str(path))
    checker: ScopeChecker = ScopeChecker(path, set())
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
    cells: object = document.get("cells", [])
    sources: list[str] = []
    if isinstance(cells, list):
        cell: object
        for cell in cells:
            if isinstance(cell, dict) and cell.get("cell_type") == "code":
                lines: object = cell.get("source", "")
                joined: str = "".join(lines) if isinstance(lines, list) else str(lines)
                sources.append("\n".join(line for line in joined.splitlines() if not line.lstrip().startswith(("%", "!"))))
    return "\n".join(sources)


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


def main(argv: list[str] | None = None) -> int:
    """Run the checker over the given paths.

    Args:
        argv: Command-line arguments, defaulting to ``sys.argv[1:]``.

    Returns:
        1 when any violation is found, otherwise 0.
    """
    parser: argparse.ArgumentParser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    args: argparse.Namespace = parser.parse_args(argv)

    violations: list[Violation] = []
    path: Path
    for path in iter_python_files(args.paths):
        try:
            violations.extend(check_source(path, read_source(path)))
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
    }
)
PROTECTED_SUFFIXES: tuple[str, ...] = ("/tools/check_declarations.py", "/.claude/settings.json", "/.claude/settings.local.json")
PROTECTED_DIRECTORIES: tuple[str, ...] = ("/.github/workflows/", "/tools/hooks/")
FILE_TOOLS: frozenset[str] = frozenset({"Edit", "Write", "MultiEdit"})
SHELL_TOOLS: frozenset[str] = frozenset({"Bash", "PowerShell"})

# Every protected file as it can appear in a command. One alternation serves both
# patterns below, so a redirect is checked against exactly the files that are named.
PROTECTED_TARGETS: str = "(?:" + "|".join(re.escape(name) for name in sorted(PROTECTED_NAMES)) + r"|\.github[/\\]workflows|tools[/\\]check_declarations\.py|tools[/\\]hooks|\.claude[/\\]settings)"
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
    normalized: str = "/" + path.replace("\\", "/").lstrip("/").casefold()
    name: str = normalized.rsplit("/", 1)[-1]
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
gates passed.

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
CHANGED_LINES: tuple[str, ...] = ("uv", "run", "diff-cover", "coverage.xml", "--compare-branch=main", "--include-untracked", "--fail-under=100")
COVERAGE_XML: Path = Path("coverage.xml")
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
    result: Result
    if files:
        lint: tuple[str, ...] = ("uv", "run", "pre-commit", "run", "--files", *files)
        result = run(lint)
        if result.returncode != 0:
            return " ".join(lint), result
    result = run(TESTS)
    if result.returncode != 0:
        return " ".join(TESTS), result
    unrecorded: list[str] = unrecorded_modules(files, read_coverage())
    if unrecorded:
        listing: str = "\n".join(f"  {path}" for path in unrecorded)
        return "coverage record check", Result(1, f"No coverage record for:\n{listing}\nNo test imports these modules, so none of their lines are measured and diff-cover skips them. Add a test that exercises each one.")
    result = run(CHANGED_LINES)
    if result.returncode != 0:
        return " ".join(CHANGED_LINES), result
    return None


def unrecorded_modules(files: list[str], report: str) -> list[str]:
    """Return the changed ``.py`` files the coverage report has no record of.

    Notebooks are exempt: pytest-cov never measures them.
    """
    recorded: set[str] = {html.unescape(name) for name in COVERAGE_FILENAME.findall(report)}
    return [path for path in files if path.endswith(".py") and path not in recorded]


if __name__ == "__main__":
    raise SystemExit(main())
STOPEOF

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

printf '\nInstalling the pre-commit git hook...\n'
uv run pre-commit install

# The checks read the files git tracks, so stage first. This is the state you
# are about to commit anyway (see "Next" below).
printf '\nStaging files so the checks can see them...\n'
git add -A

# Read-only: each tool runs directly in report mode, never through pre-commit.
# A repository that already had a .pre-commit-config.yaml keeps it, and its
# hooks (ruff --fix, end-of-file-fixer, Black) would rewrite files if run.
CHECK_RC=0
NOT_RUN=()

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

printf '\n=========================================================\n'
printf 'Created: %s\n' "${CREATED[*]:-(none)}"
printf 'Skipped: %s\n' "${SKIPPED[*]:-(none)}"
printf '=========================================================\n'

if [ "${#SKIPPED[@]}" -gt 0 ]; then
    printf '\nSkipped files already existed and were NOT changed. If pyproject.toml\n'
    printf 'is among them, merge the [tool.*] sections by hand. If .claude/settings.json\n'
    printf 'is among them, merge its "hooks" block by hand.\n'
fi

if [ "${#NOT_RUN[@]}" -gt 0 ]; then
    printf '\nNot run, because this project does not install them: %s\n' "${NOT_RUN[*]}"
    printf 'Add the [dependency-groups] dev entries from the baseline pyproject.toml,\n'
    printf 'run "uv sync --all-groups", then re-run the checks.\n'
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
