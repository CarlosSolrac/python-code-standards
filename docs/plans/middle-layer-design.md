# Plan: a stronger middle layer — design shape, outside-in TDD, a pass-through check, and an eval

Source material: the daytime review of 2026-10-23, which traced weak middle layers to the guidance in
[python-code-standards/skill/SKILL.md](../../python-code-standards/skill/SKILL.md) (lines 72–74),
[python-code-standards/skill/references/testing.md](../../python-code-standards/skill/references/testing.md) (lines 5–13),
[CLAUDE.md](../../CLAUDE.md) (lines 14–15, 24–25) and [design-spec/skill/SKILL.md](../../design-spec/skill/SKILL.md)
(§2, rules 2, 3 and 10, the import contract, §9). Where this plan and anything else differ, this plan wins.

The findings, in short:

1. Fakes fix each helper's interface from the caller's side before the helper exists, and no step revisits it.
2. "Collaborators injected as fakes" contradicts `testing.md`'s own rule that only I/O, time, randomness and the network are faked.
   Middle-layer tests then assert delegation, not results.
3. "Least code" applied top level first makes each level delegate to the next: the pass-through functions design-spec rule 2 deletes.
4. Domain-outward design stops at components; inside a unit, and in every Small design, top-down is the only method. design-spec
   §9 never re-checks rules 2–3 against the code.
5. "No extra abstractions" tips close calls toward procedural step functions.
6. Related: the layer list `cli, io, core, common` has no use-case layer, so sequencing and per-unit-of-work error handling have no home.

The remedies: types first (domain states as types), outside-in TDD (acceptance test per use case, unit tests through the public API,
fakes only at ports), Ousterhout's deep-module red flags as rule 2 at function level, an `app` layer, and a mechanical pass-through check.

## Decisions already made by the user

Do not reopen these; log a decision only for choices this plan leaves open.

- **Task 2's wording is fixed** below. Apply it as written; change it only where a check fails, and log each change as a decision.
- **`<prefix>_app` sits beside `<prefix>_io`**, below `cli`: `layers = ["<prefix>_cli", "<prefix>_app | <prefix>_io", "<prefix>_core",
  "<prefix>_common"]`. Confirm the `|` syntax for independent layers in import-linter's documentation first. If it is not supported, list
  `<prefix>_app` above `<prefix>_io` and add a `forbidden` contract from `<prefix>_app` to `<prefix>_io`; log that.
- **A pass-through** is a `def` or `async def` whose body, apart from a leading docstring, is one statement — `return <call>` or a bare
  `<call>` (awaited or not) — whose arguments are exactly the function's own parameters, each passed once and unchanged (positionally,
  by keyword, or as `*args`/`**kwargs`), in any order, excluding `self` and `cls`. The callee may be any expression, so
  `return self._inner.total()` on a method with no other parameters is one. A call that adds a constant, or transforms or omits an
  argument, is not. Functions decorated `@overload` or `@abstractmethod` are skipped. Only `.py` files. Output one `path:line name` per
  finding; exit 1 when any is found, 0 otherwise.
- **Eval 7**: `files: []`; prompt "Write a module that loads orders from a CSV file, keeps the latest version of each order by
  order_id, and writes daily revenue to a DuckDB table, with tests."; `tests`: "middle-layer shape: pass-through count on a multi-step
  task with no design hint". `grade.py` gains a `passthroughs` field, filled by running the tool as a subprocess the way
  `count_declarations` runs its checker.
- **Skill version**: `python-code-standards` 4.3.0 → 4.4.0.
- **Stacking**: tasks 2 and 3 branch from task 1's branch and are independent of each other.
- **Not tonight**: wiring `check_passthrough.py` into `python-code-standards/skill/assets/pre-commit-config.yaml` (hooks
  configuration); the layer lists in `template-sqlmesh-duckdb` (another repository); running eval 7 (a real session). Do not attempt them.

## Tasks

| # | Task | Depends on | Done-check |
|---|---|---|---|
| 1 | `check_passthrough.py`, test-first | — | From `python-code-standards/`: `uv run pytest tests/test_check_passthrough.py --cov=skill.tools.check_passthrough --cov-branch --cov-report=term-missing` at 100% statement and branch; Ruff check and format, `check_declarations.py`, Pyright, MyPy, complexipy and deptry clean on the new files; the tool exits 1 on a sample pass-through and 0 on `skill/assets/conformance.py`; `bash skill/tools/mutation.sh 'skill.tools.check_passthrough*'` leaves no survivor that is not killed or recorded in `docs/mutation-equivalents.md` |
| 2 | Guidance rewrite in four files | 1 (stacked) | `git grep -n -e "interface you want them to have" -e "collaborators injected as fakes" -e "one level down at a time" -- ':!docs/plans'` prints nothing; `node design-spec/skill/tools/validate_mermaid.mjs design-spec/skill/SKILL.md` exits 0; the node test command below passes at 100% line and branch; `design-spec/skill/SKILL.md` has at most 250 lines; the `hooks:` frontmatter of `design-spec/skill/SKILL.md` is unchanged |
| 3 | Eval 7 and a pass-through count in `grade.py` | 1 (stacked) | `evals.json` parses and has eval 7; `uv run pytest tests/test_grade.py --cov=evals.grade --cov-branch` at 100%; same lint and type gates as task 1 on changed files; the test count in `evals/RUNBOOK.md` §2 equals what `uv run pytest -q` reports |

Node test command (from the repository root):
`node --test --experimental-test-coverage --test-coverage-include="design-spec/skill/tools/*.mjs" --test-coverage-lines=100 --test-coverage-branches=100 "design-spec/tests/*.test.mjs"`

Python checks run from `python-code-standards/`, on the paths listed in its README (*Verifying the skill itself*), plus the new files.

### 1. `check_passthrough.py`

`python-code-standards/skill/tools/check_passthrough.py`, tests in `python-code-standards/tests/test_check_passthrough.py`, under the
`python-code-standards` skill, in the shape of `check_declarations.py`: a CLI taking files or directories, standard library `ast` only.
The definition is in the decisions above; each clause gets a test, including the near misses (an added constant, a transformed argument,
a dropped argument, a decorated `@overload`). `skill/tools` is already in mutmut's `source_paths`, so no configuration changes.

Run it on `skill/tools`, `evals` and `tests` and list what it finds in the PR body. Do not fix those: they are out of scope.

### 2. Guidance rewrite

Apply each replacement exactly. Change nothing else in these files.

**`python-code-standards/skill/references/testing.md`**: replace the section from `## Test-first, top-down` up to (not including)
`## Coverage` with:

~~~markdown
## Test-first, outside-in

1. **Types first.** Name the domain states the unit moves data through and declare each as a type (frozen dataclass, Pydantic model, or `Literal`-tagged record), so each function maps one state to the next. Parse input once, at the edge, into a type that carries its invariant.
2. **Outer loop.** Write one failing acceptance test per use case, through the composition root, with in-memory adapters (DuckDB `:memory:`, a fake HTTP client) behind the ports. It stays red until the use case works end to end.
3. **Red.** Write one failing test against the unit's public API and run it alone (`uv run pytest <test_file>::<test_name> -q`); confirm it fails for the expected reason — a missing function or a wrong result, not an import typo or a broken fixture.
4. **Green.** Write the least production code that passes.
5. **Refactor** with the suite green. Helpers are extracted here, each named for the decision it owns, and are tested through the public API; give one its own tests only when it holds independently complex logic. Commit the step if the repository's workflow asks for it.
6. **Ascend.** Look at each new helper from its caller: change an interface that no longer fits, and merge any function that only forwards its arguments (`check_passthrough.py` finds them). Repeat from step 3 until the acceptance test passes.

Ports — I/O, time, randomness, the network — arrive through parameters or constructor injection as protocols, so a test swaps them without patching; unit tests replace them with fakes and nothing else. In-process collaborators are real. The acceptance tests cover the real wiring.
~~~

**`python-code-standards/skill/SKILL.md`**: set `version: 4.4.0`. Replace the three bullets under `## Design and testing` with:

~~~markdown
- **Design shape.** Architecture is designed from the domain outward, per the `design-spec` skill, and so is each unit: its domain states are types, and its functions map one state to the next. Sketching a unit top-down — the entry point, then the calls it needs — is a way to find those states, not the order to build it in. Every function owns a decision. Red flags, fixed before review: a function that only forwards its arguments, functions split by time order (load, then validate, then write) rather than by what each one knows, an interface about as complex as its implementation, and two functions that depend on the same detail. A type that names a domain state, or a function for one use case, is not an extra abstraction.
- **Test-driven development.** No production code without a failing test that demands it. Outer loop: one acceptance test per use case, through the composition root with in-memory adapters. Inner loop: red, one failing test against the unit's public API, watched failing for the expected reason; green, the least code that passes; refactor with the suite green, extracting helpers there. Then ascend: revisit each new helper's interface from its caller.
- **Unit tests.** Fakes replace only ports — I/O, clocks, randomness, the network — injected as protocols. In-process collaborators are real, and helpers are tested through the public API unless they hold independently complex logic.
~~~

Under `## Verification`, in the code block, after the `check_declarations.py` line, add:

~~~bash
uv run python "${CLAUDE_SKILL_DIR}/tools/check_passthrough.py" <files>   # not in pre-commit; run it in both cases
~~~

**`CLAUDE.md`**, *Before writing code*: replace the bullet `- Design architecture from the domain outward, ... one level at a time.` with:

~~~markdown
- Design from the domain outward, per the `design-spec` skill, down to each unit: domain
  states are types, functions map one state to the next, and every function owns a
  decision. No function only forwards its arguments. Top-down is for sketching, not
  for build order.
~~~

*While writing code*: replace the first bullet with:

~~~markdown
- Build only what was asked. No extra features, options, abstractions, or handling for cases
  that cannot occur. A type that names a domain state, or a function for one use case, is
  not an extra abstraction.
~~~

**`design-spec/skill/SKILL.md`**:

- §2 step 1 becomes: `1. Name the domain concepts and the states each moves through. In code, each state becomes a type and each transition a function from one state type to the next.`
- §3, the component flowchart paragraph: `(ingestion, pure core, data path, assurance, storage, orchestration as they exist)` becomes `(ingestion, pure core, use cases, data path, assurance, storage, orchestration as they exist)`.
- §3, the import contract: the sentence ending `never the ones above:` gains, before the colon, `; layers joined by | sit side by side and may not import each other`. The TOML block becomes:

  ~~~toml
  [tool.importlinter]
  root_packages = ["<prefix>_cli", "<prefix>_app", "<prefix>_io", "<prefix>_core", "<prefix>_common"]

  [[tool.importlinter.contracts]]
  name = "Dependencies point inward"
  type = "layers"
  layers = ["<prefix>_cli", "<prefix>_app | <prefix>_io", "<prefix>_core", "<prefix>_common"]
  ~~~

  (or the fallback in the decisions above, if `|` is unsupported).
- Rule 2 becomes: `Every layer, model, component, and function owns a decision. One that only forwards or reshapes data without enforcing a rule is deleted. Red flags: a function that only forwards its arguments; steps split by time order rather than by what each hides; an interface as complex as its implementation; two units that depend on the same detail.`
- Rule 3 becomes: `One responsibility per component: ingestion (adapters), transformation (models or pure core), use cases (sequencing and per-unit-of-work error handling, through Protocols), and orchestration (composition root) are separate. The composition root chooses adapters and calls; it never transforms, queries, or writes files itself.`
- Rule 10 becomes: `Design from the domain outward: concepts and states first, then map inputs and outputs onto them. Each state is a type and each transition a function.`
- §9: after `Python code follows the \`python-code-standards\` skill.` add the sentence `Once implemented, re-apply rules 2 and 3 to the code, every function as well as every component, and update the component flowchart where the code differs (rule 14).`

Do not touch the `hooks:` frontmatter.

### 3. Eval 7 and the pass-through count

- `python-code-standards/evals/evals.json`: add eval 7 as decided above.
- `python-code-standards/evals/grade.py`, test-first in `tests/test_grade.py`: a `count_passthroughs(target, tool)` that runs
  `check_passthrough.py` as a subprocess and counts its findings; `Score.passthroughs: int`; a `--passthrough` argument defaulting to
  `skill/tools/check_passthrough.py`; the field in the `--json` output and in whatever summary `grade.py` prints. Bump the grader
  version recorded in each result, since results gain a field.
- `python-code-standards/evals/RUNBOOK.md` §2: the test count. `python-code-standards/README.md` *Reading the result*: one paragraph —
  a pass-through count that does not drop with the skill means the design-shape rule is not landing.

## Morning steps (for the user, not nightshift)

1. Open `.nightshift/LOG-<date>.md`; read *Morning summary* and *Needs you* first. Then close the nightshift session and start a fresh
   one: until the log is `complete` it denies every prompt.
2. Mark the draft PRs ready and merge task 1, then tasks 2 and 3, retargeting each to `main` after task 1 merges.
3. Pull `main` in `/home/carlos/_src/python-code-standards`: `~/.claude/CLAUDE.md` and the skill links point at that checkout, so the
   new rules reach sessions only then.
4. Run eval 7, both arms, per `python-code-standards/evals/RUNBOOK.md`.
5. Decide whether to add `check_passthrough.py` to `python-code-standards/skill/assets/pre-commit-config.yaml` (hooks configuration),
   and whether to add the `app` layer to `template-sqlmesh-duckdb`.
