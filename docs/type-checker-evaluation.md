# Type checker evaluation: ty, Pyre, Pyrefly

Date: 2026-10-16. Task: TODO.md, "Evaluate TY, PYRE, PYREFLY". Each tool ran ephemerally through
`uvx`. None of them was added to `pyproject.toml`, `uv.lock`, the templates, pre-commit or CI.

## Recommendation

**Keep Pyright and MyPy, both strict, as the gate. Add none of the three now.**

| Tool | Verdict | One-line reason |
|------|---------|-----------------|
| ty (Astral) | Revisit later | Very fast, but it accepts entirely unannotated code, ignores the repository's `# type: ignore[code]` comments, and is still 0.0.x, with new rules arriving between weekly releases |
| Pyrefly (Meta) | Revisit later; the strongest of the three | Agrees with MyPy on this code and found one real nit, but cannot replace either checker. Its imported config does not check unused ignores, private use or unreachable code |
| Pyre (Meta) | Do not adopt | Deprecated in favour of Pyrefly. No Windows build, 4 false positives on 6,465 lines, and it missed two seeded defects that every other checker caught |

The reasons are in the sections below. The last section lists what would change each verdict.

## What was run

Scope: the README's own check scope, run from `python-code-standards/`. That is
`skill/tools skill/assets/conformance.py tests evals/grade.py`: 26 tracked Python files,
6,465 lines.

Machine: Windows 11, uv 0.11.29, project Python 3.13.14 (`uv sync --all-groups`). Pyre has no
Windows wheel, so it ran in WSL 2 (Ubuntu, uv 0.12.24, Python 3.13.15). It checked a scratch copy
of the same tracked files, with `conftest.py` and the two package `__init__.py` files added so
imports resolve. A Linux virtual environment was synced from the same `uv.lock`.

Versions. The repository's plans take the newest release that is at least two weeks old, so the
primary run uses that release. A second run uses the newest release, to show how fast results move
(decision D21 in the nightshift log).

| Tool | Primary | Newest | Command (from `python-code-standards/`) |
|------|---------|--------|------------------------------------------|
| Pyright | 1.1.411 (locked) | 1.1.414 | `uv run pyright skill/tools skill/assets/conformance.py tests evals/grade.py` |
| MyPy | 2.4.0 (locked) | 2.4.0 | `uv run mypy skill/tools skill/assets/conformance.py tests evals/grade.py` |
| ty | 0.0.84 (2026-09-24) | 0.0.89 (2026-10-16) | `uvx ty@0.0.84 check <scope>` |
| Pyrefly | 1.3.2 (2026-09-28) | 1.4.0 (2026-10-15) | `uvx pyrefly@1.3.2 check <scope>` |
| Pyre | 0.9.25 (2025-07-07, the last type-checker release) | 0.10.0 (2026-08-06, repackaged as Pysa) | in WSL: `uvx --from pyre-check==0.9.25 pyre --source-directory . --search-path <site-packages> check` |

`<scope>` is the same four paths as in the Pyright command. Each extra mode is the same command
with one flag added: ty `--error all`; Pyrefly `--preset strict` or `--preset all`; Pyre `--strict`.

### Baseline: Pyright and MyPy

Both are clean on the scope: Pyright `0 errors, 0 warnings, 0 informations`, MyPy
`Success: no issues found in 26 source files`.

Two things the baseline turned up about how the checks are run:

- Bare `uv run pyright`, with no paths, reports 60 errors. Every one is in `evals/fixtures/`,
  which is non-conforming on purpose. `[tool.pyright]` has no `include` or `exclude` to skip it.
- Bare `uv run mypy` fails with "Missing target module, package, files, or command." `[tool.mypy]`
  sets no `files`.
- The README's *Verifying the skill itself* lists neither type checker. They run through the
  skill's verification steps (`uv run pyright <files> && uv run mypy <files>`), the setup script's
  whole-repository check and the pre-commit template.

## Findings on this repository

| Tool and mode | Diagnostics | Verdict |
|---------------|-------------|---------|
| ty 0.0.84 and 0.0.89, default rules | 5 errors (the same in both versions) | 3 false positives, plus 2 hits on a deliberate mismatch that is already suppressed (ty ignores the suppression) |
| ty, `--error all` | 54 (0.0.84), 57 (0.0.89) | the 5 above, 26 missing `@override`, 23 "unsound" `Any` or `Unknown` assignments; 0.0.89 adds 3 from a new rule |
| Pyrefly 1.3.2 and 1.4.0, mypy settings imported (preset `legacy`) | 0 errors, 1 warning, 2 suppressed | 1 true positive (minor) |
| Pyrefly, `--preset strict` | 26 errors and the warning | 26 missing `@override` |
| Pyrefly, `--preset all` | 297 (1.3.2), 290 (1.4.0) | mostly unused call results and implicit bool conversion |
| Pyre 0.9.25 and 0.10.0 | 4 errors (the same in both) | 4 false positives |
| Pyre, `--strict` | 12 errors | the 4 above, plus 8 "Invalid decoration" on `@pytest.mark.no_mutation` |

### ty

- `skill/assets/conformance.py:76`, two errors: `case [head, *rest]:` "Object of type
  `list[object] | list[Json] | list[str]` is not assignable to `list[Json]`". **False positive.**
  `payload` is the recursive alias `Json`, and a sequence pattern can only match its
  `list[Json]` arm. ty narrows this pattern too loosely. Pyright, MyPy and Pyrefly accept it.
- `skill/tools/check_declarations.py:183` and `:196`: `self.visit_For(node)` passes an
  `ast.AsyncFor` where `ast.For` is declared. **Already known.** The mismatch is deliberate and
  suppressed with `# type: ignore[arg-type]`. ty honours only a bare `# type: ignore` or its own
  `# ty: ignore[rule]`, never a mypy-coded one. A scratch file confirmed this: `type: ignore[arg-type]`
  and even `type: ignore[invalid-argument-type]` were reported; bare `type: ignore` was not.
  Adopting ty would mean a second suppression syntax. `check_suppressions.py` does not cover it yet.
- `skill/tools/setup_files.py:359`: `parts: list[str] = (key or "").split(".")` gives "`list[str] |
  list[LiteralString]` is not assignable to `list[str]`". **False positive.** The `""` literal
  picks `str.split`'s `LiteralString` overload, and ty does not widen it to the declared type.
- `--error all` turns on opt-in rules. `unsound-assignment` and `unsound-return-statement` flag 23
  places where an `Any` or `Unknown` value meets a declared type. Most come from `json.loads`, as
  in `data: dict[str, object] = json.loads(...)`; the rest from DuckDB's `fetchall` and AST
  attributes in `skill/tools`. Declaring the type at that boundary is the house style, and Pyright
  and MyPy accept it.
  `missing-override-decorator` asks for `@override` on 26 `ast.NodeVisitor` methods, a rule the
  standards do not use. 0.0.89 adds `truthiness-test-of-none-union`, which fires 3 times. The
  opt-in rule set is still changing between weekly releases.

### Pyrefly

Without a `[tool.pyrefly]` table, Pyrefly imports `[tool.mypy]` and prints "using settings imported
from `[tool.mypy]` ... (preset: legacy)". In a scratch copy, `pyrefly init` produced the same
mapping: `unannotated-return`, `implicit-any`, `no-any-return` and `implicit-any-parameter` as
errors, and `redundant-cast` as a warning. It took nothing from `[tool.pyright]`, which this file also has.

- `skill/tools/review_brief.py:191`: `found.update(str(item) for item in group if isinstance(item,
  str))` gives "Unnecessary `str()` call; argument is already of type `str`". **True positive**,
  harmless dead code that neither Pyright nor MyPy reports. It is pre-existing and was left alone.
- The two `# type: ignore[arg-type]` comments are honoured ("2 suppressed").
- `--preset strict` adds only `missing-override-decorator` (26). `--preset all` is a lint pass, for
  example `unused-call-result` on every ignored `int` return; the standards do not ask for that.

### Pyre

- `conformance.py:78`: `case {"name": str() as name}` gives "name is declared to have type `str` but
  is used as type `Json`". **False positive.** Pyre does not narrow class patterns.
- `check_declarations.py:310` (`node.args.vararg.arg` after `is not None`) and `:438`
  (`node.name` after `is not None`) give "Optional type has no attribute" and "expected `str` but
  got `Optional[str]`". **False positives.** Pyre does not narrow attribute chains.
- `tests/test_review_brief.py:119`: a list comprehension assigned to a declared
  `list[dict[str, object]]` is inferred as `List[Dict[str, Union[int, str]]]`. **False positive.**
  Pyre does not infer the comprehension against the declared type.
- `--strict` adds "Pyre was not able to infer the type of the decorator `pytest.mark.no_mutation`"
  8 times.

## Strictness: a seeded-defect probe

Clean code shows false positives but not misses. So a scratch file with 17 seeded defects (18
checks; reproduced in the appendix) ran through every checker. Pyright and MyPy used a copy of
this repository's `pyproject.toml`; the others used the modes shown.

Y = reported as an error, w = reported as a warning (ty's default exit code is still 1),
– = not reported.

| # | Defect | Pyright strict | MyPy strict | ty | ty `--error all` | Pyrefly (mypy import) | Pyrefly strict | Pyre `--strict` |
|---|--------|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| C01 | unannotated function | Y | Y | – | – | Y | Y | Y |
| C02 | missing return annotation | – | Y | – | – | Y | – | Y |
| C03 | `str \| None` passed as `str` | Y | Y | Y | Y | Y | Y | Y |
| C04 | wrong return type | Y | Y | Y | Y | Y | Y | Y |
| C05 | missing return on one path | Y | Y | Y | Y | Y | Y | Y |
| C06 | attribute typo | Y | Y | Y | Y | Y | Y | Y |
| C07 | too many arguments | Y | Y | Y | Y | Y | Y | Y |
| C08 | `Any` returned as `int` | – | Y | – | Y | Y | – | – |
| C09a | always-true `isinstance` | Y | – | – | Y | – | – | – |
| C09b | unreachable statement | – | Y | – | – | – | – | – |
| C10 | redundant `cast` | – | Y | – | – | – | – | – |
| C11 | unused `# type: ignore` | Y | Y | w | Y | – | – | – |
| C12 | possibly unbound name | Y | – | – | Y | – | Y | Y |
| C13 | coroutine never awaited | Y | Y | w | Y | Y | Y | – |
| C14 | incompatible override | Y | Y | Y | Y | Y | Y | Y |
| C15 | `TypedDict` missing key | Y | Y | Y | Y | Y | Y | Y |
| C16 | protected member used outside its class | Y | – | – | – | – | – | – |
| C17 | `list[object]` returned as `list[str]` | Y | Y | Y | Y | Y | Y | – |
| | **caught, of 18** | 14 | 15 | 10 | 13 | 12 | 11 | 10 |

- Two Pyright misses come from how the probe is written. Pyright infers return types, so C02 is
  not an error under its strict mode. `cast(int, 1)` narrows `Literal[1]` to `int`, so Pyright's
  `reportUnnecessaryCast` does not treat it as redundant; MyPy does.
- Pyright and MyPy together catch all 18, and each catches some the other misses (C02, C08, C09b,
  C10 versus C09a, C12, C16). That is the case for running both, as `references/typing.md` does.
- All five agree on the plain bugs (C03–C07, C14, C15). They differ on the hygiene checks the
  standards rely on: annotation completeness, unused suppressions, private use and unreachable code.
- None of the three new tools caught a defect that Pyright or MyPy missed.
- ty does not check annotations at all. It ran clean on `evals/fixtures/`, where Pyright reports
  60 errors, MyPy 4 and Pyrefly 11 (9 in strict). Pyre did not run on the fixtures.
- Pyre missed C17, a real type error, and C13.

## Speed

Wall time for the full scope, five runs each, read from the clock; startup cost included.
`uv run python -c pass` takes about 113 ms here and `uvx ty --version` about 82 ms.

| Tool | Five runs (ms) | Note |
|------|----------------|------|
| Pyright 1.1.411 | 2137, 2135, 2107, 2116, 2143 | mostly the PyPI wrapper and Node.js startup |
| MyPy 2.4.0, warm cache | 700, 333, 328, 331, 333 | cold with `--no-incremental`: about 1,540 |
| ty 0.0.84 / 0.0.89 | about 152 / about 155 | |
| Pyrefly 1.3.2 / 1.4.0 | about 249 / about 295 | |
| Pyre 0.9.25 (WSL) | about 2,000 | with a search path of only the 7 packages the scope imports. With the whole `site-packages`, read across the WSL `/mnt/c` bridge: about 255,000. A one-file project takes about 1,300 |

At 6,500 lines every checker finishes in about two seconds or less. ty and Pyrefly would save
about two seconds per run, which does not matter at this size. It would matter for a large
codebase or for a check on every keystroke.

## Configuration parity

| | Reads this repository's config | Strict mode | Per-path relaxation (like `skill/tools`) | Suppression comments |
|---|---|---|---|---|
| Pyright | `[tool.pyright]` | `typeCheckingMode = "strict"` | `executionEnvironments` (in use) | `# pyright: ignore[rule]`, `# type: ignore` |
| MyPy | `[tool.mypy]` | `strict = true`, `warn_unreachable` | per-module `[[tool.mypy.overrides]]` | `# type: ignore[code]` |
| ty | only `[tool.ty]`; ignores both tables above | none; `--error all` or per-rule levels | `[[tool.ty.overrides]]` (worked in a scratch config) | bare `# type: ignore`, `# ty: ignore[rule]`; mypy codes not honoured |
| Pyrefly | imports `[tool.mypy]`; took nothing from `[tool.pyright]` | `preset = "strict"` or per-error levels | `[[tool.pyrefly.sub-config]]` (worked in a scratch config) | `# type: ignore[...]`, `# pyrefly: ignore` |
| Pyre | only `.pyre_configuration` (CLI flags used here) | `--strict` / `strict: true` | per-file `# pyre-strict` / `# pyre-unsafe` | `# pyre-ignore`, `# pyre-fixme`, `# type: ignore` |

Matching the repository's strict settings with ty is not possible today, because it has no
annotation-completeness rules. With Pyrefly it is close: the imported mypy settings cover
annotations and `Any` returns. They do not cover unused ignores, which `--preset all` reports, or
private use, which nothing reports. Its strict preset adds `@override`, which the standards do not
require.

## Maturity, release cadence and licence

From PyPI metadata (classifiers, release dates) on 2026-10-16.

| Tool | Maintainer | Status | Licence | First release | Releases in the last 90 days | Platforms |
|------|------------|--------|---------|---------------|------------------------------|-----------|
| Pyright | Microsoft | stable, 1.1.x | MIT | 2019 | 3 | any (Node.js) |
| MyPy | python/mypy | stable, 2.x | MIT | 2012 | 2 | any |
| ty | Astral | Beta, 0.0.x (no stability promise) | MIT | 2025-04-30 (0.0.0a1) | 29 (about two a week) | Windows, macOS, Linux wheels |
| Pyrefly | Meta | Production/Stable, 1.x | MIT | 2025-02-19 | 15 (a minor about every five weeks, plus patch and dev releases) | Windows, macOS, Linux wheels |
| Pyre (pyre-check) | Meta | the type checker is deprecated: the 0.9.25 page says "Check out Pyrefly, our next-generation Python typechecker"; 0.10.0 describes itself as Pysa, "historically bundled with Pyre, Meta's (deprecated) type checker" | MIT | 2018 | 0 (last: 0.10.0, 2026-08-06) | manylinux x86_64 and macOS arm64 only; no Windows |

## What would change the verdicts

- **ty**: ty gains rules for missing annotations (C01, C02) and either honours mypy-coded
  `# type: ignore[...]` or the standards accept `# ty: ignore[...]`, with `check_suppressions.py`
  extended to match. A release past 0.0.x with a stable rule set would also count. Then trial it
  as a third, fast pre-commit check, not as a replacement.
- **Pyrefly**: re-run this evaluation on a larger or slower codebase, where its speed matters. Try a
  `[tool.pyrefly]` table that turns on `unused-type-ignore` and the annotation errors, and replace
  MyPy only if it then matches MyPy's column of the probe, or nearly. It still reports nothing for
  C16 (Pyright's `reportPrivateUsage`), so Pyright would stay.
- **Pyre**: nothing. Its successor is Pyrefly.

Changing the standards (`skill/SKILL.md`, `references/typing.md`, `assets/pyproject-baseline.toml`)
is your decision; this report changes none of them.

## Appendix: the probe

Saved as `probe.py` next to a copy of `python-code-standards/pyproject.toml`, then run with
`uv run --project <repo>/python-code-standards pyright probe.py`, the same for `mypy`,
`uvx ty@0.0.84 check probe.py`, `uvx pyrefly@1.3.2 check probe.py` and, in WSL,
`uvx --from pyre-check==0.9.25 pyre --strict --source-directory . check`.

```python
"""Seeded defects: one per numbered case, each on the line its comment names."""

import json
from typing import TypedDict, cast


def c01(x):  # C01 missing parameter and return annotations
    return x


def c02(x: int):  # C02 missing return annotation only
    return x


def c03(s: str | None) -> int:
    return len(s)  # C03 None passed where str is required


def c04() -> int:
    return "x"  # C04 wrong return type


def c05(flag: bool) -> int:  # C05 missing return on one path
    if flag:
        return 1


def c06() -> str:
    return "abc".uper()  # C06 attribute typo


def c07() -> None:
    c04(1)  # C07 too many arguments


def c08(s: str) -> int:
    data = json.loads(s)
    return data["a"]  # C08 returning Any from a function declared to return int


def c09(x: int) -> int:
    if isinstance(x, int):  # C09a unnecessary isinstance
        return 1
    return 2  # C09b unreachable statement


def c10() -> int:
    return cast(int, 1)  # C10 redundant cast


def c11() -> int:
    y: int = 1  # type: ignore  # C11 unused type: ignore
    return y


def c12(flag: bool) -> int:
    if flag:
        z: int = 1
    return z  # C12 possibly unbound


async def c13_coro() -> int:
    return 1


async def c13() -> None:
    c13_coro()  # C13 coroutine never awaited


class Base:
    def run(self, n: int) -> int:
        return n


class Child(Base):
    def run(self, n: str) -> int:  # C14 incompatible override
        return len(n)


class Movie(TypedDict):
    title: str
    year: int


def c15() -> Movie:
    return {"title": "x"}  # C15 TypedDict missing key


class Holder:
    _secret: int = 1


def c16() -> int:
    return Holder()._secret  # C16 private member used outside its class


def c17(rows: list[object]) -> list[str]:
    out = []  # C17 empty container whose element type is never declared
    for r in rows:
        out.append(r)
    return out  # C17 list[object] returned as list[str]
```
