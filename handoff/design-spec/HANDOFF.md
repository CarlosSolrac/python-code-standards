# Handoff: add a `design-spec` skill to python-code-standards

Written 2026-10-12 by a cloud session, for a Claude Code session in VS Code in this repository. Everything you need is in this folder:

- `HANDOFF.md`: this file. Context, decisions already made, conflicts with this repo's rules, and the tasks.
- `SKILL.draft.md`: the complete skill as it stands. It is named `.draft.md` so nothing installs it by accident.

Nothing outside `handoff/` was changed, and nothing was committed. This repo's global rules apply to you: post a plan for more than two
files and wait, and ask before committing.

---

## 1. The problem this solves

When the user gives inputs and outputs and lets Claude design everything, the top and bottom layers come out fine and the middle layers
come out poorly: pass-through layers, mixed responsibilities, dicts between stages, Python doing work DuckDB should do, and no dependency
direction. The ends are anchored by real constraints (sources, consumers); the middle has no anchor, so it becomes glue.

**This repo is probably part of the cause.** Both `CLAUDE.md` ("Design top-down: the entry point first, then each helper it calls, one
level at a time") and `python-code-standards/skill/SKILL.md` ("Top-down design. Write the public entry point first...") tell Claude to
design from the entry point inward. That is a good way to *implement* a unit; it is the wrong way to *architect* a system, because the
middle gets shaped by whatever the entry point happened to call.

The fix the user agreed to: design from the domain outward (concepts and states first), make every middle component own a decision, put
typed contracts at every boundary, and show the design as a short diagrammed spec for approval before writing code.

## 2. What the skill does

Two modes, one size gate, 14 rules, each rule paired with the diagram that shows it.

- **Design mode**: new system or restructure. Sizes the request, models the domain and the numbers first, produces a spec
  (state diagram, component flowchart, boundary contract table, and more by size), and **stops for approval**.
- **Document mode**: an existing project. Derives the same spec from the code, marks what is inferred, and lists rule deviations as
  findings, labelled new or known. Changes no code.

Size gate: Small (at most two layers and under ~150 lines: no spec), Standard (one process: full spec, plus a C4 context view when it touches
two or more external systems), Large (several processes: adds a C4 container view).

Diagrams are text only (Mermaid, Markdown tables, directory trees), because they are cheap in tokens and diff well.

## 3. What has been verified

| Claim | How it was verified |
|---|---|
| The reference skeleton (section 10 of the draft) works | Built and run in a cloud workspace with SQLMesh 0.236.3 and DuckDB 1.5.6: ruff, `mypy --strict`, pytest (2), `sqlmesh test` (2), and a full run from an empty warehouse all passed |
| Audits block bad data | A negative amount made the run exit 1; the downstream mart kept its last good state |
| Same-day reruns pick up new data | Only with the restatement plan in `transform()`; without it the run exits 0 and silently ignores new rows |
| Model changes stay tested | Changing a model without its unit test made `sqlmesh plan` refuse to run |
| Document mode works on a real project | Run on ParquetToXL (25,587 lines, 11 workspace packages); result merged as PR #7 in `CarlosSolrac/ParquetToXL` (`docs/design.md`, `docs/backlog2.md`) |
| The Mermaid validator in section 7 catches errors | All diagrams parsed; a deliberately broken one failed |

**Not verified:** incremental (`INCREMENTAL_BY_TIME_RANGE`) models, Python models, a dlt adapter, and rendering with mermaid-cli (it needs
a headless Chrome the cloud workspace could not download; it should work on the user's machine).

The skeleton project itself is not in any repository. It lived in an ephemeral cloud workspace and was sent to the user as
`sqlmesh-skeleton.zip`. Every file of it is reproduced in section 10 of the draft, so the draft is the copy of record.

## 4. Decisions already made, with the user

- **Stack**: Python 3.13+, uv, DuckDB, SQLMesh for transformations, ports and adapters for ingestion, one composition root.
- **SQLMesh with an exit path** (ADR-0001 in the draft): plain DuckDB SQL only, no Jinja, no macros beyond `@this_model` and the
  incremental time macros, version pinned. Chosen after checking maintenance: active releases, Linux Foundation governance since March
  2026, but pre-1.0 and owned by the same company that owns dbt.
- **Replace and restate** (ADR-0002): adapters replace raw tables; the composition root restates downstream on every run.
- **Document mode cross-references** existing specs, decision records, and audits instead of restating them.
- **The size gate** also lives in the user's memory preferences as a one-line rule, so it applies when the skill does not load. That line
  defers to this skill when it is available.

## 5. Conflicts with this repository: decide these first

This repo's README says each rule lives in exactly one file. The draft was written standalone, so it breaks that in five places.

| # | Conflict | Where | Recommendation |
|---|---|---|---|
| 1 | "Design top-down: the entry point first" contradicts rule 10 (design from the domain outward) | `CLAUDE.md`, *Before writing code*; `python-code-standards/skill/SKILL.md`, *Design and testing* | Keep top-down as the **implementation** order inside a unit; say architecture comes from the domain outward and defer to `design-spec` for it. Edit both lines |
| 2 | "More than two files, or a new dependency: post a numbered plan and wait" overlaps the size gate | `CLAUDE.md` | Keep both: the plan is about edits, the spec is about design. Add one sentence saying a Standard or Large design produces a spec first, and the plan follows its approval |
| 3 | Section 9 of the draft (uv, typing, line length, declarations, stubs, verification commands) duplicates the Python skill | `SKILL.draft.md` §9 vs `python-code-standards/skill/SKILL.md` | Delete §9 from the skill and replace it with "Python code follows the `python-code-standards` skill." Keep only the SQLMesh-specific lines (`sqlmesh test`, the `PlanError` CLI tip) |
| 4 | `CsvSource` builds DDL with f-strings from a config identifier, with no allowlist; this repo forbids that and never suppresses Ruff `S608` | `SKILL.draft.md` §10 vs `references/sql-duckdb.md` lines 5–6 | Add an allowlist check of `table_name` (and its schema) in the adapter and a test for the rejection. Rule 8's "identifier-only DDL... from typed config" should cite the allowlist requirement |
| 5 | The skeleton's ruff `select` list is far narrower than this repo's baseline (no `S`, `ANN` partial, no `D` config parity), and it uses mypy only, not pyright | `SKILL.draft.md` §10 `pyproject.toml` vs `skill/assets/pyproject-baseline.toml` | Replace the skeleton's tool config with a pointer to the baseline, then rerun the skeleton under it and fix what fires |

Precedence in `CLAUDE.md` is request → project `CLAUDE.md` → skill → global file, so when `design-spec` loads it already outranks
conflict 1. The edit is still needed, because the global line applies whenever the skill does not load.

## 6. Tasks

Post this as your plan, adjusted after reading the repo, and wait for approval (more than two files).

| Step | Do | Check |
|---|---|---|
| 1 | Settle conflicts 1–5 with the user | User's answers recorded in the plan |
| 2 | Create `design-spec/skill/SKILL.md` from the draft, mirroring `python-code-standards/skill/`. Move the reference skeleton (§10) and the worked example (§8) to `design-spec/skill/references/` so `SKILL.md` stays short | `SKILL.md` under ~250 lines; references linked from it |
| 3 | Apply the conflict resolutions (edit the two top-down lines, delete §9, fix `CsvSource`, align tool config) | `git diff` shows each rule in exactly one file |
| 4 | Put the skeleton under `design-spec/skill/assets/skeleton/` as real files, so it can be run rather than copied out of Markdown | `uv run ruff check`, `uv run pyright`, `uv run mypy`, `uv run pytest`, `uv run sqlmesh test`, and `uv run project` from an empty warehouse all pass under this repo's baseline config |
| 5 | Put the validator script in `design-spec/skill/tools/validate_mermaid.mjs` and reference it instead of inlining it | Runs on `SKILL.md` and on ParquetToXL's `docs/design.md`; a broken block fails |
| 6 | Add `design-spec/evals/evals.json` following `nightshift/evals/` (see §7 for cases) | Each eval has a prompt, expected output, and assertions |
| 7 | Update `README.md`: what the skill is, install links for bash, PowerShell, and cmd (the same three forms the README uses now) | Links resolve; `ls -l ~/.claude/skills/design-spec/SKILL.md` shows the link |
| 8 | Ask before committing, per `CLAUDE.md` | |

## 7. Suggested evals

1. **Design, Standard.** "Pull orders from a CSV and a REST API into DuckDB, dedupe, and produce a daily revenue table." Assert: sized
   Standard; state diagram before components; every component labelled with a decision; contract table; stops with "Approve or
   correct before I implement." and writes no code.
2. **Design, Small.** "Script to convert one CSV to Parquet." Assert: no spec, no SQLMesh; code written directly.
3. **Document, real repo.** Point it at a ParquetToXL checkout at `8ffaa6f`. Assert: finds the `pqx-report` dependency defect with an
   `!`/`d` matrix; finds the `CLAUDE.md` layering drift; labels backlog item 9.1 as known; changes no code.
4. **Resync.** Change one import in a documented fixture, ask to resync. Assert: reports the matrix change before overwriting.

## 8. Open items, not for this session

- The user has an unsaved claude.ai skill card with the same draft. Once this repo is the source of truth, either skip saving the card or
  treat the repo version as the master and re-save the card from it, so the two do not drift.
- Untested paths listed in §3.
- ParquetToXL's fixes are tracked in its own `docs/backlog2.md` and will be handled by a separate session.

## 9. References

- ParquetToXL design map and findings: `CarlosSolrac/ParquetToXL`, PR #7 (merged): `docs/design.md`, `docs/backlog2.md`.
- SQLMesh: <https://github.com/SQLMesh/sqlmesh> (releases and Linux Foundation governance checked 2026-10-12).
