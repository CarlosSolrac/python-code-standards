---
name: python-code-standards
version: 2.3.0
description: Standards for writing, editing, and reviewing Python. Produces strictly typed, documented, localized changes verified by execution, Ruff, a type checker, and tests. Use whenever Python is written, modified, refactored, reviewed, or debugged — including small edits, scripts, notebooks, and tests — and whenever a project's Python tooling, dependencies, or configuration change.
---

# Python Code Standards

Strictly typed, documented Python. Localized changes, verified by execution.

Assume competent Python by default. This file covers only what overrides a default or is easy to drift from under pressure.

## Precedence

Current request → repository configuration (`pyproject.toml`, `ruff.toml`, `pyrightconfig.json`, `mypy.ini`, pytest and coverage config) → this document → tool defaults.

Report conflicts; never resolve them silently. Configuration contradicting this document is a conflict to raise, not a file to edit.

## Variable declaration

**Every variable is annotated before its first binding** — loop targets, `with` targets, unpacked names, match captures, class-body aliases, and instance attributes — using a PEP 526 bare annotation ahead of the statement:

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

Exempt because the language cannot annotate them: comprehension and generator targets (write an explicit loop when the type matters), `except ... as` names, walrus bindings, imports.

`check_declarations.py` enforces this across modules and notebook code cells. Use the repository's own `tools/check_declarations.py` when it has one, since that is the copy CI and pre-commit run; otherwise invoke the bundled copy at `${CLAUDE_SKILL_DIR}/tools/check_declarations.py`. It runs in the verification loop, so treat its output as the specification. Match captures and instance attributes are covered; comprehension targets are not. An in-file base class's declarations cover its subclasses. `B007` fires on a declared target unused in the body — rename to `_name`, keeping the declaration.

## Before implementing

State assumptions that change the solution. Present competing interpretations rather than picking silently; stop and ask when requirements are ambiguous or conflicting. Say so when a simpler approach would do, or when the requested one adds complexity, conflicts with a repository constraint, or weakens correctness — then recommend the smallest safer alternative.

Build only what was asked: no speculative features, extension points, config options, or abstractions for a single caller.

Define observable success criteria first, and for a bug fix, how it is reproduced. Keep overhead proportional — a trivial change needs a sentence, not a plan.

## Scope

The default failure mode is a diff larger than the request.

- Every changed line traces to the request, a required test, required documentation, or verification remediation.
- Preserve unrelated behavior, formatting, imports, names, and comments. Match local patterns in the modified area even where another approach would normally be preferred.
- Report unrelated problems and pre-existing dead code; don't fix or delete them. Remove only what *this* change made unused.
- Never replace a whole function or file for a localized edit.
- Limit Ruff to changed files; preview with `ruff format --diff` and narrow the scope if it would rewrite unrelated content.
- Inspect the diff before finishing.

## Environment

`uv` for everything, Python 3.13+ (`requires-python = ">=3.13"`, Ruff `target-version = "py313"`).

```bash
uv venv                  uv add <pkg>            uv sync
uv python pin 3.13       uv add --dev <pkg>      uv run <command>
```

Every tool runs through `uv run` so the verified environment is the project environment; `uvx` only for non-dependencies. Runtime deps in `[project] dependencies`, tooling in `[dependency-groups] dev`. Commit `uv.lock` for applications, not libraries — run `uv lock` once and commit it before CI, since `assets/ci.yml` installs with `--locked`. Never migrate build backends, dependency managers, or layouts unasked.

## Formatting and documentation

Ruff is authoritative and the checked-in config is the specification — don't restate its rules in prose or review. Line length **220**. `assets/pyproject-baseline.toml` is the baseline for a new project.

Never auto-apply unsafe fixes: inspect with `ruff check --unsafe-fixes --diff`, check `ruff rule <CODE>`, apply only when the behavioral effect is understood and tested.

Google-style docstrings on every module, class, and non-trivial function in source (optional in tests, where the name carries the meaning), describing the contract rather than narrating the implementation. `Args:`/`Returns:`/`Raises:` only where they add what the name and annotations don't. Never document `self`/`cls` or repeat annotations in prose. Comments explain *why*, and are updated whenever the code they describe changes — staleness is the failure mode for prose attached to code.

## Verification

Changed files only, through `uv run`, using the project's commands where they differ.

```bash
# 1. Execute the changed code through the narrowest practical entry point.
# 2. Lint, format, declarations, and both type checkers:
uv run pre-commit run --files <files>
# In a repository that has not adopted the tooling, run the bundled checker:
uv run python "${CLAUDE_SKILL_DIR}/tools/check_declarations.py" <files>
# 3. Tests and coverage:
uv run pytest <tests> -q
uv run pytest <tests> --cov=<module> --cov-report=term-missing --cov-branch
```

`assets/pre-commit-config.yaml` defines those hooks. Where the repository has no pre-commit setup, run the tools individually: `ruff check --fix`, `ruff format`, the declaration checker, `pyright`, `mypy`.

Coverage on changed code: **90% statement, 85% branch**, both reported. If missed, say what is uncovered rather than lowering the threshold.

**Never claim anything passed unless the command ran and its output was observed.** Editor diagnostics don't substitute — an IDE bridge like `mcp__ide__getDiagnostics` is read-only, often absent, and covers only analyzed files, so an empty result is indistinguishable from an unanalyzed one.

When commands can't run, don't imply results. Open with `UNVERIFIED — no execution environment; nothing below was run.`, give the code and tests, list the exact commands in order, and state which claims depend on them. "This should pass" is not that notice.

## Suppressions

`# noqa`, `# type: ignore`, `# pyright: ignore`, `# pragma: no cover`, per-file ignores, disabled diagnostics, coverage omissions, `fail_under` reductions, and warning filters all require explicit authorization. Attempt a real fix first; if a genuine tool limitation remains, explain the diagnostic, why code can't fix it, and the narrowest suppression — then wait. Never weaken coverage to make it pass. `PGH` rejects blanket directives, and `RUF100` flags ones that stopped applying — both are enforcement, not advice.

## Reporting

Changed files, tests added, exact commands run, pass/fail with measured coverage, and anything unrun or unresolved. No placeholder ellipses in copy-ready code.

## References

- `assets/` — templates to copy into a repository: `pyproject-baseline.toml`, `pre-commit-config.yaml`, and `ci.yml`, which runs everything above plus a conformance check that fails when a tooling upgrade drifts from these standards
- `assets/conformance.py` — a module in house style that passes the whole toolchain; read it instead of asking how something should look
- `references/typing.md` — annotation decisions; always when a dependency ships no types
- `references/sql-duckdb.md` — Python constructs, executes, or embeds SQL
- `references/testing.md` — writing or changing tests
- `references/domains.md` — Pydantic, concurrency, packaging, dependency security
