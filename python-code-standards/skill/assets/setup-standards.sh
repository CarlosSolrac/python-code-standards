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
#   .github/workflows/ci.yml    CI: pre-commit --all-files + pytest --cov
#   tools/check_declarations.py the "annotate before first binding" checker
#   tools/__init__.py           makes tools importable as a package
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

[tool.coverage.run]
branch = true

[tool.coverage.report]
fail_under = 90
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

      - name: Tests and coverage
        run: uv run pytest --cov --cov-report=term-missing --cov-branch
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

# pre-commit only sees files git tracks, so stage first. This is the state you
# are about to commit anyway (see "Next" below).
printf '\nStaging files so the checks can see them...\n'
git add -A

printf '\nRunning the full check over all files...\n'
PRECOMMIT_RC=0
uv run pre-commit run --all-files || PRECOMMIT_RC=$?
git add -A # re-stage anything the ruff hook reformatted on this first run

# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #

printf '\n=========================================================\n'
printf 'Created: %s\n' "${CREATED[*]:-(none)}"
printf 'Skipped: %s\n' "${SKIPPED[*]:-(none)}"
printf '=========================================================\n'

if [ "${#SKIPPED[@]}" -gt 0 ]; then
    printf '\nSkipped files already existed and were NOT changed. If pyproject.toml\n'
    printf 'is among them, merge the [tool.*] sections by hand.\n'
fi

if [ "$PRECOMMIT_RC" -eq 0 ]; then
    printf '\npre-commit: PASS\n'
else
    printf '\npre-commit: exited %s -- read the output above.\n' "$PRECOMMIT_RC"
    printf 'On a fresh repo the first run may reformat the files it just created;\n'
    printf 're-run "uv run pre-commit run --all-files" and it should pass.\n'
fi

printf '\nNext (files are already staged):\n'
printf '  git commit -m "Add python-code-standards toolchain"\n'
printf '  # uv.lock is committed for an application; delete it + switch ci.yml for a library\n'

exit "$PRECOMMIT_RC"
