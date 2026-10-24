"""Report functions that only forward their arguments.

A pass-through is a ``def`` or ``async def`` whose body, apart from a leading
docstring, is one statement: ``return <call>`` or a bare ``<call>``, awaited or
not.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


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
    findings: list[Finding] = [Finding(path, node.lineno, node.name) for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _forwarded_call(node) is not None]
    return sorted(findings, key=lambda finding: finding.line)


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
