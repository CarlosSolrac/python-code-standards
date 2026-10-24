"""Report functions that only forward their arguments.

A pass-through is a ``def`` or ``async def`` whose body, apart from a leading
docstring, is one statement: ``return <call>`` or a bare ``<call>``, awaited or
not. The call's arguments are exactly the function's own parameters, each passed once
and unchanged (positionally, by keyword, or as ``*args``/``**kwargs``), in any order,
leaving out ``self`` and ``cls``. The callee may be any expression.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

_DECLARATION_DECORATORS: frozenset[str] = frozenset({"overload", "abstractmethod"})
"""Decorators marking a function whose body is not its implementation; such functions are never reported."""


@dataclass(frozen=True)
class Finding:
    """A function that does nothing but forward its arguments."""

    path: Path
    line: int
    name: str


def find_passthroughs(path: Path, source: str) -> list[Finding]:
    """Return every pass-through in one module, in source order.

    Args:
        path: File path, used for reporting.
        source: Module source text.

    Returns:
        One finding per pass-through ``def`` or ``async def``, including methods and nested functions.
    """
    tree: ast.Module = ast.parse(source)
    findings: list[Finding] = [Finding(path, node.lineno, node.name) for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not _is_declaration(node) and _forwards_exactly(node)]
    return sorted(findings, key=lambda finding: finding.line)


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
