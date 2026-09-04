---
name: python-code-standards
version: 4.0.0
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
| match capture, class-body alias, instance attribute | required |
| comprehension or generator target | exempt — write an explicit loop when the type matters |
| `except ... as` name, walrus, import | exempt — the language cannot annotate these |

```python
row: dict[str, object]
for row in rows:
    ...

class Ingest:
    total: int          # declared in the class body

    def __init__(self) -> None:
        self.total = 0
```

Prefer dataclasses and Pydantic models over plain classes for anything holding state — their fields *are* class-body annotations, so they satisfy the attribute rule by construction. A plain class is the right choice when construction logic is non-trivial or the class inherits from a non-dataclass base.

`check_declarations.py` enforces this across modules and notebook code cells, and its output is the specification. Use the repository's own `tools/check_declarations.py` when it has one, since that is the copy CI and pre-commit run; otherwise `${CLAUDE_SKILL_DIR}/tools/check_declarations.py`. An in-file base class's declarations cover its subclasses. `B007` fires on a declared target unused in the body — rename to `_name`, keeping the declaration.

## Scope

- Run Ruff on changed files only. Preview with `ruff format --diff`; narrow the scope if it would rewrite unrelated content.
- Do not add `pyproject.toml`, tests, a lockfile, or config the request did not ask for, even to make verification runnable. Run what the repository supports; report the rest as unrun.
- Report pre-existing defects; do not fix them. One exception: a security defect on a line the change already touches — fix it and say so.

## Environment

`uv` for everything, Python 3.13+ (`requires-python = ">=3.13"`, Ruff `target-version = "py313"`).

```bash
uv venv                  uv add <pkg>            uv sync
uv python pin 3.13       uv add --dev <pkg>      uv run <command>
```

Every tool runs through `uv run` so the verified environment is the project environment; `uvx` only for non-dependencies. Runtime deps in `[project] dependencies`, tooling in `[dependency-groups] dev`. Commit `uv.lock` for applications, not libraries — run `uv lock` once and commit it before CI, since `assets/ci.yml` installs with `--locked`.

## Formatting and documentation

Ruff is authoritative and the checked-in config is the specification — don't restate its rules in prose or review. Line length **220**. `assets/pyproject-baseline.toml` is the baseline for a new project.

Never auto-apply unsafe fixes: inspect with `ruff check --unsafe-fixes --diff`, check `ruff rule <CODE>`, apply only when the behavioral effect is understood and tested.

Google-style docstrings on every module, class, and non-trivial function in source (optional in tests, where the name carries the meaning), describing the contract rather than narrating the implementation. `Args:`/`Returns:`/`Raises:` only where they add what the name and annotations don't. Never document `self`/`cls` or repeat annotations in prose. Comments explain *why*, and are updated whenever the code they describe changes. No placeholder ellipses in copy-ready code.

## Verification

Changed files only, through `uv run`, using the project's commands where they differ.

```bash
# 1. Execute the changed code through the narrowest practical entry point.
# 2. Lint, format, declarations, and both type checkers (pre-commit is in the dev group):
uv run pre-commit run --files <files>
# Repository without pre-commit: run the tools individually.
uv run ruff check --fix <files> && uv run ruff format <files>
uv run python "${CLAUDE_SKILL_DIR}/tools/check_declarations.py" <files>
uv run pyright <files> && uv run mypy <files>
# 3. Tests and coverage:
uv run pytest <tests> -q
uv run pytest <tests> --cov=<module> --cov-report=term-missing --cov-branch
```

Coverage on changed code: **90% statement, 85% branch**, both reported. If missed, say what is uncovered; never lower the threshold.

**Never claim anything passed unless the command ran and its output was observed.** Editor diagnostics such as `mcp__ide__getDiagnostics` are not verification (see `references/typing.md`). When commands cannot run, open the reply with `UNVERIFIED — nothing below was run.`, list the exact commands in order, and state which claims depend on them.

## Suppressions

`# noqa`, `# type: ignore`, `# pyright: ignore`, `# pragma: no cover`, per-file ignores, disabled diagnostics, coverage omissions, `fail_under` reductions, and warning filters all require explicit authorization. Attempt a real fix first. If a genuine tool limitation remains, explain the diagnostic, why code can't fix it, and the narrowest suppression — then wait. `PGH` rejects blanket directives, and `RUF100` flags ones that stopped applying.

## References

- `assets/` — templates to copy into a repository: `pyproject-baseline.toml`, `pre-commit-config.yaml`, `gitattributes`, and `ci.yml`
- `assets/conformance.py` — a module in house style that passes the whole toolchain; read it instead of asking how something should look
- `references/typing.md` — annotation decisions and checkers; always when a dependency ships no types
- `references/sql-duckdb.md` — Python constructs, executes, or embeds SQL
- `references/testing.md` — writing or changing tests
- `references/domains.md` — Pydantic, concurrency, packaging, dependency security
