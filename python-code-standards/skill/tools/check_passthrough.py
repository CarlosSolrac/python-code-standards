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
