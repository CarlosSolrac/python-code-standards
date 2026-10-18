# Plan: design-spec review items, eval coverage, a mechanical grader, and a tool evaluation

Source material: items 2–7 of [TODO.md at c743325](https://github.com/CarlosSolrac/python-code-standards/blob/c743325/TODO.md),
approved 2026-10-17 from the review of the "LLM Visualization Standard", and the prep session of 2026-10-17. Where this plan and
TODO.md differ, this plan wins.

## Decisions already made by the user

Do not reopen these; log a decision only for choices this plan leaves open.

- **One branch for items 2–7** (task 1). They all edit the §3 table and the diagram conventions in `design-spec/skill/SKILL.md`;
  one branch avoids six conflicting PRs. Order inside it: 6, 3, 4, 2, 5, 7 (C4 removal first, so items 3 and 4 can mark flowcharts).
- **Evals are written, not run, overnight.** A design-spec eval is a real Claude Code session graded by hand (see
  `design-spec/evals/RUNBOOK.md`); a session started tonight would load `main`'s skill through `~/.claude/skills`, not the branch's.
  Done-checks are therefore static: `evals.json` parses, assertions exist, answer keys match the new rules, diagrams parse, tests
  pass. Running the evals is a morning step.
- **Item 4 gets a new eval 6** on the existing `fixtures/planted-defects` workspace (no new fixture), prompt below.
- **Eval 4 moves to ParquetToXL at `f8f4a41`**, which already has a `docs/design.md`, instead of waiting for the empty
  `template-sqlmesh-duckdb`. It gets its own bundle; the eval 3 bundle (`8ffaa6f`) stays as it is, because a bundle reaching
  `f8f4a41` would let eval 3's agent read its answer key from git history.
- **A mechanical grader** at `python-code-standards/evals/design_spec_grade.py`, tests in `python-code-standards/tests/`, under the
  `python-code-standards` skill. That location is already covered by the project's pytest, Ruff, Pyright and MyPy configuration, so
  no configuration changes. It grades only what a tool can decide; judgment assertions stay manual. Same shape as
  `evals/grade.py`: a CLI, `--json` output, every result from a tool.
- **grimp is already a dev dependency** (`grimp>=3.17,<4`, added in daytime 2026-10-17). Its checks come last (task 5), in a task
  of their own.
- **Graphify** is evaluated, not adopted (task 4).
- **Not tonight** — do not attempt them:
  - TODO.md item 1 (filling `template-0-summaries` / `template-sqlmesh-duckdb`), and the part of item 6 that changes those
    repositories' worked examples. Other repositories.
  - Adding `evals/design_spec_grade.py` to `[tool.mutmut] source_paths`. Tool configuration.
  - Running any eval session.
  - Adding graphify or any other evaluated tool as a dependency, or installing a skill into `~/.claude`.

## Tasks

| # | Task | Depends on | Done-check |
|---|---|---|---|
| 1 | design-spec review items 2–7, plus eval 6 | — | all of: `git grep -nE "C4Context\|C4Container" -- ':!docs/plans'` prints nothing; `node design-spec/skill/tools/validate_mermaid.mjs design-spec/skill/SKILL.md design-spec/evals/expected/eval-3/design.md README.md` exits 0; the node test command below passes at 100% line and branch; `evals.json` parses, every eval has `prompt`, `expected_output`, `assertions`, and eval 6 exists; each item's assertion named below is present |
| 2 | Eval 4 on ParquetToXL `f8f4a41` | 1 (stacked: both edit `evals.json`) | `bash design-spec/evals/build-fixture.sh 4 <empty dir>` builds a fixture whose `git log --oneline -1` is the build commit and whose code has exactly the one reversed import (`git diff f8f4a41 --stat` shows one file); `evals.json` parses; RUNBOOK's fixture table has the new row |
| 3 | Grader: text and diagram checks | 2 (stacked) | `uv run pytest --cov=skill.tools --cov=evals.grade --cov=evals.design_spec_grade --cov-branch` at 100%; Ruff check and format, `check_declarations.py`, Pyright, MyPy, complexipy, deptry all clean on the new files; run on `expected/eval-3/design.md` it reports every mechanical eval 3 assertion as pass |
| 4 | Evaluate graphify and doc/spec knowledge tools | — | `docs/graphify-evaluation.md` exists with the four sections below and a recommendation; every measured number names the command that produced it |
| 5 | Grader: import-graph checks with grimp | 3 (stacked) | as task 3's checks; on the planted-defects fixture the grader's computed dependency matrix equals the one in `expected/eval-3b/answer-key.md` |

Node test command (from the repository root):
`node --test --experimental-test-coverage --test-coverage-include="design-spec/skill/tools/*.mjs" --test-coverage-lines=100 --test-coverage-branches=100 "design-spec/tests/*.test.mjs"`

Python checks run from `python-code-standards/`, on the paths listed in its README (*Verifying the skill itself*), plus the new files.

### 1. design-spec review items 2–7, plus eval 6

All in `design-spec/skill/SKILL.md` unless named. Report the skill's line count in the PR; it was 209 before this task.

- **Item 6 — replace `C4Context`/`C4Container` with `flowchart` + boundary subgraphs.** Mermaid's C4 is experimental, lays out
  poorly, and ignores `classDef`, so items 3–4 can't mark it. Change artifacts #2–#3 in §3 and every other file that names them:
  `README.md`, `design-spec/evals/evals.json` (eval 1's assertion and expected output), `design-spec/evals/expected/eval-3/design.md`,
  `design-spec/tests/validate_mermaid.test.mjs`. Keep the meaning: the context view shows each external system as its own node
  outside the system boundary subgraph. `docs/plans/design-spec.md` is a record; leave it.
- **Item 3 — inferred marker.** Inferred nodes get a `?` label suffix and `classDef inferred stroke:#555,stroke-dasharray:5 5`
  (dashed border). Dashed arrows stay reserved for Protocols (§7); don't use them for inference. Add a short diagram example to §7.
  Eval 3b's "marked inferred" assertion names the marker.
- **Item 4 — change-impact diagram.** New artifact #15, design mode restructuring an existing codebase only: a `flowchart` with
  `classDef added` / `changed` / `removed`; reusable as the PR-description diagram. Add eval 6 to `evals.json` and its row to
  RUNBOOK's fixture table:
  - fixture `fixtures/planted-defects` (build id 6, reuse eval 3b's build);
  - prompt: "Restructure tally: remove the tally-stage pass-through and replace the dict that daily_revenue returns with a typed
    record. Design the change.";
  - assertions: design mode on an existing codebase; a change-impact flowchart with the three classDefs; `tally-stage` marked
    removed; `tally-core`, `tally-io` and `tally-cli` marked changed; every `changed` or `removed` node names a module that exists in
    the fixture and every `added` one names a module that does not; every diagram passes the checker; no code is written.
- **Item 2 — evidence citations (document mode).** Add a `source` column (`path:line`) to the boundary contract table and to the
  dependency matrix footnote; every non-inferred node in the component flowchart cites one. Replaces "facts read from code are
  stated plainly" (§4 step 6). Update `evals/expected/eval-3/design.md` and the eval 3b answer key; add an assertion to evals 3 and 3b
  that every cited `path:line` exists in the fixture.
- **Item 5 — grain and key in the contract table.** Columns become `boundary | input | output | grain/key | invariants | owner`
  (§3); with item 2 the table also has `source`. Update eval 1's contract-table assertion and the answer keys.
- **Item 7 — OpenAPI pointer.** One line in §3: if the project exposes an HTTP API, the contract table cites its OpenAPI file.

### 2. Eval 4 on ParquetToXL `f8f4a41`

- Make `design-spec/evals/fixtures/parquettoxl-f8f4a41.bundle` from `https://github.com/CarlosSolrac/ParquetToXL`: a branch at
  `f8f4a41` only (`git bundle create`), so nothing after it is inside. Leave `parquettoxl-8ffaa6f.bundle` as it is.
- `build-fixture.sh 4`: clone the new bundle, then reverse one import and commit it as the build commit. Choose an import between
  two packages that `docs/design.md`'s dependency matrix shows as one-directional, so the reversal is a new `!` or cycle the matrix
  must show; record the choice as a decision. Remove the "template has no docs/design.md" failure path.
- Rewrite eval 4's `expected_output` and assertions for this fixture: before `docs/design.md` is overwritten, the reply reports the
  changed import; the resynced matrix shows it; a rule 6 finding cites the file and line (item 2); no code changes.
- Update RUNBOOK's prerequisites and fixture table (eval 4 no longer needs network or the template).

### 3. Grader: text and diagram checks

`python-code-standards/evals/design_spec_grade.py`, test-first under the `python-code-standards` skill. Input: an eval id, the fixture
folder, and its build commit. Output: one line per assertion it can decide (pass / fail with the evidence), `manual` for the rest;
`--json` as in `evals/grade.py`. Checks:

- every Mermaid block passes `design-spec/skill/tools/validate_mermaid.mjs` (run it as a subprocess);
- required classDefs present (`inferred`; for eval 6 `added`, `changed`, `removed`) and no `C4Context`/`C4Container`;
- contract table header equals the §3 columns;
- every cited `path:line` exists in the fixture at the build commit;
- first line states the mode and size class; the eval 1 closing line;
- no code changed: `git diff --stat <build commit>` lists documentation files only (eval 1: `git status` lists only `docs/`).

Update `python-code-standards/README.md`'s verify commands to add `--cov=evals.design_spec_grade`, and `design-spec/evals/RUNBOOK.md`
§5 to run the grader before grading by hand.

### 4. Evaluate graphify and doc/spec knowledge tools

(approved: run tools via `uvx` or `npx`, in folders under `<repo-parent>/python-code-standards.nightshift/scratch/`; build fixtures
there too; web searches and reading project pages are fine; do not add any tool as a dependency; do not install skills into
`~/.claude`; do not set up API keys. If a tool needs one of those, record what it needs and evaluate what runs without it.)

Write `docs/graphify-evaluation.md`:

1. **Graphify on code.** Run it on the planted-defects fixture and ParquetToXL at `f8f4a41`. Compare what design-spec's document
   mode must read with and without the graph (files read, tokens where measurable) and whether the graph's dependencies match the
   answer keys.
2. **Graphify on docs and specs.** Run it on this repository's `docs/`, the two skills' `SKILL.md` files and ParquetToXL's `docs/`.
   Record what indexing them needs and costs, and whether a few concrete questions about them come back right.
3. **Other tools.** Search for tools that index or manage docs and specs for coding agents. Compare up to three, plus graphify, on:
   local versus model-based indexing, cost, licence, maintenance, and fit with design-spec's spec files.
4. **Recommendation.** Adopt one (and where it would plug into design-spec), or adopt none, with the reasons.

### 5. Grader: import-graph checks with grimp

Add to `design_spec_grade.py`, test-first: build the fixture's import graph with `grimp.build_graph` (put each `packages/*/src`, or
the fixture's source root, on `sys.path` first; do not install the fixture), and check:

- the spec's dependency matrix (`Y` / `!` / `d`) equals the computed one, with `!` and `d` from comparing imports with each package's
  declared dependencies;
- for eval 4, the reversed import appears in the resynced matrix;
- for eval 6, the module-existence rule for `changed` / `removed` / `added` nodes, using grimp's module list instead of file paths.

## Morning steps (for the user, not nightshift)

1. Open `.nightshift/LOG-<date>.md`; read *Morning summary* and *Needs you* first.
2. Mark the draft PRs ready and merge in order: task 1, then 2, 3, 5, retargeting each to `main` after its base merges. Task 4 is
   independent.
3. Add the grader to mutation testing: in `python-code-standards/pyproject.toml`, `[tool.mutmut] source_paths = ["skill/tools",
   "evals/grade.py", "evals/design_spec_grade.py"]`; run `bash skill/tools/mutation.sh` under WSL or Linux.
4. Run the evals the review changed, per `design-spec/evals/RUNBOOK.md`: 1, 3, 3b, 4 and 6. Grade each with the new grader first,
   then the manual assertions.
5. TODO.md item 1: drop "and eval 4 can't build its fixture" (eval 4 now uses ParquetToXL). When filling the templates, give
   their worked examples item 6's flowchart context view instead of `C4Context`.
6. Read `docs/graphify-evaluation.md`. Adopting a tool is a dependency decision for a daytime session.
