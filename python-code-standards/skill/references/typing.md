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

Pylance and the IDE's `mcp__ide__getDiagnostics` bridge are not a gate: the bridge is read-only, often absent, and reports only files the editor has opened, so an empty result means "nothing analyzed" as often as "no errors". Pylance runs Pyright's engine, so `uv run pyright` gives the same diagnostics on demand.

Checker disagreement points at a real imprecision in the type model. Fix it with annotations, typed adapters, protocols, or stubs — not suppressions.

## Untyped dependencies

Stop at the first step that works. Do not skip to a suppression.

1. Check for a `py.typed` marker in the installed package — if present, nothing is needed.
2. `uv add --dev types-<package>` (typeshed).
3. Vendor-published `<package>-stubs`.
4. Write `stubs/<package>/__init__.pyi` covering only the symbols used; register via `stubPath` (Pyright) or `mypy_path` (MyPy); commit it.
5. Isolate the untyped surface behind a typed adapter or `Protocol` so the imprecision cannot spread.

Only after all five fail is a suppression a candidate, and it still needs authorization.
